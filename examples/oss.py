import asyncio
import os

import fire
import discord
import aiohttp
from bs4 import BeautifulSoup
from typing import Any

from examples.hg_parse import get_hg_articles
from examples.smtp163 import AsyncMailer
from metagpt.actions import Action
from metagpt.config import CONFIG
from metagpt.environment import Environment
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.roles.role import RoleReactMode
from metagpt.schema import Message
from metagpt.subscription import SubscriptionRunner


class CrawlOSSTrending(Action):
    async def run(self, url: str = "https://github.com/trending"):
        # return "https://github.com/trending"
        async with aiohttp.ClientSession() as client:
            async with client.get(url, proxy=CONFIG.global_proxy) as response:
                response.raise_for_status()
                html = await response.text()

        soup = BeautifulSoup(html, 'html.parser')

        repositories = []

        for article in soup.select('article.Box-row'):
            repo_info = {'name': article.select_one('h2 a').text.strip().replace("\n", "").replace(" ", ""),
                         'url': "https://github.com" + article.select_one('h2 a')['href'].strip()}

            # Description
            description_element = article.select_one('p')
            repo_info['description'] = description_element.text.strip() if description_element else None

            # Language
            language_element = article.select_one('span[itemprop="programmingLanguage"]')
            repo_info['language'] = language_element.text.strip() if language_element else None

            # Stars and Forks
            stars_element = article.select('a.Link--muted')[0]
            forks_element = article.select('a.Link--muted')[1]
            repo_info['stars'] = stars_element.text.strip()
            repo_info['forks'] = forks_element.text.strip()

            # Today's Stars
            today_stars_element = article.select_one('span.d-inline-block.float-sm-right')
            repo_info['today_stars'] = today_stars_element.text.strip() if today_stars_element else None

            repositories.append(repo_info)

        return repositories


TRENDING_ANALYSIS_PROMPT = """# Requirements
You are a GitHub Trending Analyst, aiming to provide users with insightful and personalized recommendations based on the latest
GitHub Trends. Based on the context, fill in the following missing information, generate engaging and informative titles, 
ensuring users discover repositories aligned with their interests.

# The title about Today's GitHub Trending
## Today's Trends: Uncover the Hottest GitHub Projects Today! Explore the trending programming languages and discover key domains capturing developers' attention. From ** to **, witness the top projects like never before.
## The Trends Categories: Dive into Today's GitHub Trending Domains! Explore featured projects in domains such as ** and **. Get a quick overview of each project, including programming languages, stars, and more.
## Highlights of the List: Spotlight noteworthy projects on GitHub Trending, including new tools, innovative projects, and rapidly gaining popularity, focusing on delivering distinctive and attention-grabbing content for users.
---
# Format Example

```
# [Title]

## Today's Trends
Today, ** and ** continue to dominate as the most popular programming languages. Key areas of interest include **, ** and **.
The top popular projects are Project1 and Project2.

## The Trends Categories
1. Generative AI
    - [Project1](https://github/xx/project1): [detail of the project, such as star total and today, language, ...]
    - [Project2](https://github/xx/project2): ...
...

## Highlights of the List
1. [Project1](https://github/xx/project1): [provide specific reasons why this project is recommended].
...
```

---
# Github Trending
{trending}
"""


class AnalysisOSSTrending(Action):

    async def run(
            self,
            trending: Any
    ):
        return await self._aask(TRENDING_ANALYSIS_PROMPT.format(trending=trending))


class CrawlOSSHuggingfacePapers(Action):
    async def run(self, msg: Message) -> str:
        logger.info(f"{msg}")
        return await get_hg_articles()


HG_PAPERS_ANALYSIS_PROMPT = """# Requirements
You are a Haggingface Papers Analyst, aiming to provide users with insightful and personalized consultation based on the latest
Haggingface Papers abstract. Based on the context, fill in the following missing information, generate engaging and informative titles, 
ensuring users discover articles aligned with their interests.

# The title about Today's Haggingface Papers Consultation
## Today's Haggingface Papers Consultation: Uncover the Hottest Haggingface Papers Today! Explore the trending programming languages and discover key domains capturing developers' attention. From ** to **, witness the top papers like never before.
## The Papers Categories: Dive into Today's Haggingface Papers Domains! Explore featured papers in domains such as ** and **. Get a quick overview of each paper, including upvotes, and more.
## Highlights of the List: Spotlight noteworthy papers on Haggingface Papers, including new tools, new methods, innovative papers, and rapidly gaining popularity, focusing on delivering distinctive and attention-grabbing content for users.
---
# Format Example

```
# [Title]

## Today's Haggingface Papers Consultation
Today, ** and ** continue to dominate as the most popular research areas. Key areas of interest include **, ** and **.
The top popular papers are Paper1 and Paper2.

## The Papers Categories
1. Large Language Model
    - [Paper1](https://huggingface.co/papers/paper1): [Abstract of the paper, such as upvotes total ...]
    - [Paper2](https://huggingface.co/papers/paper2): ...
...

## Highlights of the List
1. [Paper1](https://huggingface.co/papers/paper1): [provide specific reasons why this paper is recommended].
...
```

---
# Haggingface Papers
{papers}
"""


class AnalysisOSSHuggingfacePapers(Action):
    async def run(
            self,
            papers: Any
    ):
        return await self._aask(HG_PAPERS_ANALYSIS_PROMPT.format(papers=papers))


class OssWatcher(Role):
    name: str = "XiaoGang"
    profile: str = "OssWatcher"
    goal: str = "Generate an insightful GitHub Trending and Huggingface papers analysis report."
    constraints: str = "Only analyze based on the provided GitHub Trending and Huggingface papers data."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_actions([CrawlOSSHuggingfacePapers, AnalysisOSSHuggingfacePapers])
        self._set_react_mode(RoleReactMode.BY_ORDER.value)

    async def _act(self) -> Message:
        logger.info(f"{self._setting}: to do {self.rc.todo}")
        todo = self.rc.todo
        msg = self.get_memories(k=1)[0]  # find the most recent messages
        new_msg = await todo.run(msg.content)
        msg = Message(content=str(new_msg), role=self.profile, cause_by=type(todo))
        self.rc.memory.add(msg)  # add the new message to memory
        return msg


async def discord_callback(msg: Message):
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents, proxy=CONFIG.global_proxy)
    token = os.environ["DISCORD_TOKEN"]
    channel_id = int(os.environ["DISCORD_CHANNEL_ID"])
    async with client:
        await client.login(token)
        channel = await client.fetch_channel(channel_id)
        lines = []
        for i in msg.content.splitlines():
            if i.startswith(("# ", "## ", "### ")):
                if lines:
                    await channel.send("\n".join(lines))
                    lines = []
            lines.append(i)

        if lines:
            await channel.send("\n".join(lines))


async def mail_callback(msg: Message):
    async_mailer = AsyncMailer()
    await async_mailer.send(os.environ["MAIL_SENDER"], os.environ["MAIL_RECEIVER"], 'Haggingface Papers Consultation',
                            msg.content)


async def oss_callback(discord: bool = True, mail: bool = True):
    callbacks = []
    if discord:
        callbacks.append(discord_callback)

    if mail:
        callbacks.append(mail_callback)
    if not callbacks:
        async def _print(msg: Message):
            print(msg.content)

        callbacks.append(_print)

    async def callback(msg: Message):
        await asyncio.gather(*[cb(msg) for cb in callbacks])

    return callback


async def oss_trigger():
    while True:
        yield Message(content="https://github.com/trending")
        await asyncio.sleep(3600 * 24)


async def main(discord: bool = True, mail: bool = True):
    runner = SubscriptionRunner()
    callback = await oss_callback(discord, mail)
    runner.model_rebuild()
    await runner.subscribe(OssWatcher(), oss_trigger(), callback)
    await runner.run()
    # role = OssWatcher()
    # _ = asyncio.run(role.run("https://github.com/trending"))


if __name__ == "__main__":
    fire.Fire(main)
