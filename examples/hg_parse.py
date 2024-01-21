import asyncio
import json

import aiohttp
from bs4 import BeautifulSoup

from metagpt.config import CONFIG
from metagpt.logs import logger


def get_local_html_soup(url, features='html.parser'):
    with open(url, encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, features)
    return soup


async def get_html_soup(url: str):
    async with aiohttp.ClientSession() as client:
        async with client.get(url, proxy=CONFIG.global_proxy) as response:
            response.raise_for_status()
            html = await response.text()

    soup = BeautifulSoup(html, 'html.parser')
    return url, soup


def hg_article_urls(html_soup):
    _urls = []
    for article in html_soup.select('article.flex.flex-col.overflow-hidden.rounded-xl.border'):
        url = article.select_one('h3 a')['href']
        _urls.append('https://huggingface.co' + url)
    return _urls


def hg_article_infos(_url, html_soup):
    logger.info(f'Parsing {_url}')
    _article = {}
    info = html_soup.select_one('section.pt-8.border-gray-100')
    data_props = json.loads(info.select_one('div.SVELTE_HYDRATER.contents')['data-props'])
    paper = data_props['paper']
    _article['url'] = _url
    _article['id'] = paper['id']
    _article['title'] = paper['title']
    _article['upvotes'] = paper['upvotes']
    _article['publishedAt'] = paper['publishedAt']
    _article['summary'] = paper['summary']
    return _article


async def get_hg_articles():
    _, _soup = await get_html_soup("https://huggingface.co/papers")
    hg_urls = hg_article_urls(_soup)
    _soups = await asyncio.gather(*[get_html_soup(url) for url in hg_urls])
    hg_articles = map(lambda param: hg_article_infos(param[0], param[1]), _soups)

    return list(hg_articles)

if __name__ == "__main__":
    import asyncio
    for article in asyncio.run(get_hg_articles()):
        print(article)

