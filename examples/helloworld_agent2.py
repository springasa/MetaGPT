import asyncio

import fire

from metagpt.actions import Action
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message


class SimplePrint(Action):
    name: str = "SimplePrint"

    async def run(self, msg: Message) -> str:
        logger.info(f"{msg}")
        return msg + "!"


class SimplePrinter(Role):
    name: str = "XiaoGang"
    profile: str = "SimplePrinter"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_actions([SimplePrint, SimplePrint, SimplePrint])
        # self._set_react_mode(react_mode=RoleReactMode.BY_ORDER.value)

    async def _act(self) -> Message:
        todo = self.rc.todo
        msg = self.get_memories(k=1)[0]  # find the most recent messages

        start_idx = self.rc.state if self.rc.state >= 0 else 0  # action to run from recovered state
        for i in range(start_idx, len(self.states)):
            logger.info(f"{self._setting}: to do {self.rc.todo}({self.rc.todo.name})")
            self._set_state(i)
            rsp = await todo.run(msg.content)
            msg = Message(content=rsp, role=self.profile, cause_by=type(todo))
        return msg  # return output from the last action


def main():
    role = SimplePrinter()
    msg = 'Hello World!'
    result = asyncio.run(role.run(msg))
    logger.info(result)


if __name__ == "__main__":
    fire.Fire(main)