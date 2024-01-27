import asyncio
import json
import re

import aiohttp
from bs4 import BeautifulSoup

from metagpt.config import CONFIG
from metagpt.llm import LLM
from metagpt.logs import logger


def get_local_html_soup(url, features='html.parser'):
    with open(url, encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, features)
    return soup


async def get_html(url: str):
    async with aiohttp.ClientSession() as client:
        async with client.get(url, proxy=CONFIG.global_proxy) as response:
            response.raise_for_status()
            html = await response.text()

    return url, html


PROMPT_TEMPLATE = """Please extract a portion of content from HTML text to achieve the User Requirement with \
the HTML content provided in the Context.

## User Requirement
{requirement}

## Context
The html page content to be extracted is show like below:

```tree
{html}
```
"""

URLS_REQUIREMENT = "Extracting a list of URLs for Daily Papers from HTML text,"\
               "Just give me the URLs, exactly as `https://huggingface.co/papers/xxx,https://huggingface.co/papers/xxx, ...`, "\
               "don't give me python code, don't output any unnecessary characters"

def extract_urls(text):
    pattern = re.compile(r'https:\/\/huggingface\.co\/papers\/\d+\.\d+')
    return pattern.findall(text)


async def hg_article_urls(html):
    global llm
    prompt = PROMPT_TEMPLATE.format(html=html,
                                       requirement=URLS_REQUIREMENT)
    resp = await llm.aask(prompt)
    _urls = list(extract_urls(resp))
    print(', '.join(_urls))
    return _urls


ARTICLE_REQUIREMENT="Extracting a list of article infomation for Paper from HTML text," \
               "Just give me the article infomation in the json format, exactly as \
                `{'id':id, 'title':title, 'upvotes':upvotes, 'publishedAt':publishedAt, 'summary':summary}` " \
               "don't give me python code, don't output any unnecessary characters"


def extract_article(text):
    return json.loads(text.replace('```json','').replace('```',''))


async def hg_article_infos(_url, html):
    global llm
    logger.info(f'Parsing {_url}')
    prompt = PROMPT_TEMPLATE.format(html=html,
                                       requirement=ARTICLE_REQUIREMENT)
    resp = await llm.aask(prompt)
    _article = extract_article(resp)
    _article['url'] = _url
    return _article


async def get_hg_articles():
    _, _html = await get_html("https://huggingface.co/papers")
    hg_urls = await hg_article_urls(_html)
    _htmls = await asyncio.gather(*[get_html(url) for url in hg_urls])
    hg_articles = await asyncio.gather(*map(lambda param: hg_article_infos(param[0], param[1]), _htmls))

    return list(hg_articles)


if __name__ == "__main__":
    import asyncio

    llm = LLM()
    for article in asyncio.run(get_hg_articles()):
        print(article)
