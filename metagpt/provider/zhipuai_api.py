#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Desc   : zhipuai LLM from https://open.bigmodel.cn/dev/api#sdk
import json
import re
from enum import Enum
from typing import Optional, Union

from openai.types.chat import ChatCompletion
from requests import ConnectionError
from tenacity import (
    after_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)
from zhipuai.types.chat.chat_completion import Completion

from metagpt.configs.llm_config import LLMConfig, LLMType
from metagpt.logs import log_llm_stream, logger
from metagpt.provider.base_llm import BaseLLM
from metagpt.provider.constant import GENERAL_FUNCTION_SCHEMA
from metagpt.provider.llm_provider_registry import register_provider
from metagpt.provider.openai_api import log_and_reraise
from metagpt.provider.zhipuai.zhipu_model_api import ZhiPuModelAPI
from metagpt.utils.common import CodeParser
from metagpt.utils.cost_manager import CostManager
from metagpt.schema import Message


class ZhiPuEvent(Enum):
    ADD = "add"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    FINISH = "finish"


@register_provider(LLMType.ZHIPUAI)
class ZhiPuAILLM(BaseLLM):
    """
    Refs to `https://open.bigmodel.cn/dev/api#chatglm_turbo`
    From now, support glm-3-turbo、glm-4, and also system_prompt.
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self.__init_zhipuai()
        self.cost_manager: Optional[CostManager] = None

    def __init_zhipuai(self):
        assert self.config.api_key
        self.api_key = self.config.api_key
        self.model = self.config.model  # so far, it support glm-3-turbo、glm-4
        self.llm = ZhiPuModelAPI(api_key=self.api_key)

    def _const_kwargs(self, messages: list[dict], stream: bool = False) -> dict:
        kwargs = {"model": self.model, "messages": messages, "stream": stream, "temperature": 0.3}
        return kwargs

    def _cons_kwargs(self, messages: list[dict],  **extra_kwargs) -> dict:
        kwargs = {
            "messages": messages,
            "temperature": 0.3,
            "model": self.model,
        }
        if extra_kwargs:
            kwargs.update(extra_kwargs)
        #temperature 取值范围是：(0.0, 1.0)
        if float(kwargs["temperature"]) == 0.0:
            kwargs["temperature"] = 0.01
        if float(kwargs["temperature"]) == 1.0:
            kwargs["temperature"] = 0.99
        return kwargs

    def _update_costs(self, usage: dict):
        """update each request's token cost"""
        if self.config.calc_usage:
            try:
                prompt_tokens = int(usage.get("prompt_tokens", 0))
                completion_tokens = int(usage.get("completion_tokens", 0))
                self.cost_manager.update_cost(prompt_tokens, completion_tokens, self.model)
            except Exception as e:
                logger.error(f"zhipuai updats costs failed! exp: {e}")

    def completion(self, messages: list[dict], timeout=3) -> dict:
        resp: Completion = self.llm.chat.completions.create(**self._const_kwargs(messages))
        usage = resp.usage.model_dump()
        self._update_costs(usage)
        return resp.model_dump()

    async def _achat_completion(self, messages: list[dict], timeout=3) -> dict:
        resp = await self.llm.acreate(**self._const_kwargs(messages))
        usage = resp.get("usage", {})
        self._update_costs(usage)
        return resp

    async def acompletion(self, messages: list[dict], timeout=3) -> dict:
        return await self._achat_completion(messages, timeout=timeout)

    async def _achat_completion_stream(self, messages: list[dict], timeout=3) -> str:
        response = await self.llm.acreate_stream(**self._const_kwargs(messages, stream=True))
        collected_content = []
        usage = {}
        async for chunk in response.stream():
            finish_reason = chunk.get("choices")[0].get("finish_reason")
            if finish_reason == "stop":
                usage = chunk.get("usage", {})
            else:
                content = self.get_choice_delta_text(chunk)
                collected_content.append(content)
                log_llm_stream(content)

        log_llm_stream("\n")

        self._update_costs(usage)
        full_content = "".join(collected_content)
        return full_content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(min=1, max=60),
        after=after_log(logger, logger.level("WARNING").name),
        retry=retry_if_exception_type(ConnectionError),
        retry_error_callback=log_and_reraise,
    )
    async def acompletion_text(self, messages: list[dict], stream=False, timeout=3) -> str:
        """response in async with stream or non-stream mode"""
        if stream:
            return await self._achat_completion_stream(messages)
        resp = await self._achat_completion(messages)
        return self.get_choice_text(resp)

    def _func_configs(self, messages: list[dict], **kwargs) -> dict:
        """Note: Keep kwargs consistent with https://open.bigmodel.cn/dev/api#sse_example"""
        if "tools" not in kwargs:
            configs = {"tools": [{"type": "function", "function": GENERAL_FUNCTION_SCHEMA}]}
            kwargs.update(configs)

        return self._cons_kwargs(messages=messages, **kwargs)

    async def aask_code(self, messages: list[dict], **kwargs) -> dict:
        """Use function of tools to ask a code.
        Note: Keep kwargs consistent with https://platform.openai.com/docs/api-reference/chat/create

        Examples:
        >>> llm = ZhiPuAILLM()
        >>> msg = [{'role': 'user', 'content': "Write a python hello world code."}]
        >>> rsp = await llm.aask_code(msg)
        # -> {'language': 'python', 'code': "print('Hello, World!')"}
        """
        rsp = await self._achat_completion_function(messages, **kwargs)
        return self.get_choice_function_arguments(rsp)

    def _process_message(self, messages: Union[str, Message, list[dict], list[Message], list[str]]) -> list[dict]:
        """convert messages to list[dict]."""
        # 全部转成list
        if not isinstance(messages, list):
            messages = [messages]

        # 转成list[dict]
        processed_messages = []
        for msg in messages:
            if isinstance(msg, str):
                processed_messages.append({"role": "user", "content": msg})
            elif isinstance(msg, dict):
                assert set(msg.keys()) == set(["role", "content"])
                processed_messages.append(msg)
            elif isinstance(msg, Message):
                processed_messages.append(msg.to_dict())
            else:
                raise ValueError(
                    f"Only support message type are: str, Message, dict, but got {type(messages).__name__}!"
                )
        return processed_messages

    async def _achat_completion_function(self, messages: list[dict], timeout=3, **chat_configs) -> ChatCompletion:
        messages = self._process_message(messages)
        kwargs = self._func_configs(messages=messages, **chat_configs)
        rsp = await self.llm.acreate(**kwargs)
        usage = rsp.get("usage", {})
        self._update_costs(usage)
        # Temp adapt for missed values
        await self.fill_missed_values(rsp)
        return ChatCompletion(**rsp)

    async def fill_missed_values(self, rsp):
        if not rsp.get('object'):
            rsp['object'] = "chat.completion"
        if not rsp.get('choices')[0].get('message').get('content'):
            rsp.get('choices')[0]['message']['content'] = ""
        if not rsp.get('choices')[0].get('logprobs'):
            rsp.get('choices')[0]['logprobs'] = None

    def _parse_arguments(self, arguments: str) -> dict:
        """parse arguments in openai function call"""
        if "langugae" not in arguments and "code" not in arguments:
            logger.warning(f"Not found `code`, `language`, We assume it is pure code:\n {arguments}\n. ")
            return {"language": "python", "code": arguments}

        # 匹配language
        language_pattern = re.compile(r'[\"\']?language[\"\']?\s*:\s*["\']([^"\']+?)["\']', re.DOTALL)
        language_match = language_pattern.search(arguments)
        language_value = language_match.group(1) if language_match else "python"

        # 匹配code
        code_pattern = r'(["\'`]{3}|["\'`])([\s\S]*?)\1'
        try:
            code_value = re.findall(code_pattern, arguments)[-1][-1]
        except Exception as e:
            logger.error(f"{e}, when re.findall({code_pattern}, {arguments})")
            code_value = None

        if code_value is None:
            raise ValueError(f"Parse code error for {arguments}")
        # arguments只有code的情况
        return {"language": language_value, "code": code_value}

    # @handle_exception
    def get_choice_function_arguments(self, rsp: ChatCompletion) -> dict:
        """Required to provide the first function arguments of choice.

        :param dict rsp: same as in self.get_choice_function(rsp)
        :return dict: return the first function arguments of choice, for example,
            {'language': 'python', 'code': "print('Hello, World!')"}
        """
        message = rsp.choices[0].message
        if (
            message.tool_calls is not None
            and message.tool_calls[0].function is not None
            and message.tool_calls[0].function.arguments is not None
        ):
            # reponse is code
            try:
                return json.loads(message.tool_calls[0].function.arguments, strict=False)
            except json.decoder.JSONDecodeError as e:
                error_msg = (
                    f"Got JSONDecodeError for \n{'--'*40} \n{message.tool_calls[0].function.arguments}, {str(e)}"
                )
                logger.error(error_msg)
                return self._parse_arguments(message.tool_calls[0].function.arguments)
        elif message.tool_calls is None and message.content is not None:
            # reponse is code, fix openai tools_call respond bug,
            # The response content is `code``, but it appears in the content instead of the arguments.
            code_formats = "```"
            if message.content.startswith(code_formats) and message.content.endswith(code_formats):
                code = CodeParser.parse_code(None, message.content)
                return {"language": "python", "code": code}
            # reponse is message
            return {"language": "markdown", "code": self.get_choice_text(rsp)}
        else:
            logger.error(f"Failed to parse \n {rsp}\n")
            raise Exception(f"Failed to parse \n {rsp}\n")

    def get_choice_text(self, rsp: ChatCompletion) -> str:
        """Required to provide the first text of choice"""
        return rsp.choices[0].message.content if rsp.choices else ""
