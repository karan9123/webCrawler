import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import asyncio
import hashlib
from datetime import datetime, timedelta
from neo4j.time import DateTime
from scraper.robots_handler import RobotsHandler
from parsers.parser_manager import ParserManager
from playwright.async_api import async_playwright

class Scraper:
    def __init__(self, link_manager, config_manager):
        self.link_manager = link_manager
        self.config = config_manager
        self.headers = {
            'User-Agent': self.config.get('scraper.headers.user_agent'),
            'Accept': self.config.get('scraper.headers.accept'),
            'Accept-Language': self.config.get('scraper.headers.accept_language'),
            'Accept-Encoding': self.config.get('scraper.headers.accept_encoding'),
            'Connection': self.config.get('scraper.headers.connection'),
            'Upgrade-Insecure-Requests': self.config.get('scraper.headers.upgrade_insecure_requests'),
        }
        self.robots_handler = RobotsHandler(self.headers)
        self.parser_manager = ParserManager()
        self.browser = None
        self.context = None

    async def initialize(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch()
        self.context = await self.browser.new_context()

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    async def scrape_website(self, url):
        try:
            page = await self.context.new_page()
            await page.goto(url, wait_until='networkidle')
            content = await page.content()
            await page.close()
            return BeautifulSoup(content, 'html.parser')
        except Exception as e:
            print(f"Error scraping {url}: {str(e)}")
            return None

    async def discover_links(self, url, soup):
        internal_links = set()
        external_links = set()
        resource_links = set()
        base_domain = urlparse(url).netloc

        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            parsed_url = urlparse(full_url)
            
            if parsed_url.netloc == base_domain:
                if await self.robots_handler.is_allowed(full_url):
                    internal_links.add(full_url)
            elif parsed_url.scheme in ['http', 'https']:
                external_links.add(full_url)

        for tag in soup.find_all(['img', 'script', 'link']):
            src = tag.get('src') or tag.get('href')
            if src:
                full_url = urljoin(url, src)
                resource_links.add(full_url)
        
        return list(internal_links), list(external_links), list(resource_links)

    def get_content_hash(self, content):
        return hashlib.md5(content.encode()).hexdigest()

    async def should_crawl(self, url):
        last_crawl_info = self.link_manager.get_last_crawl_info(url)
        if not last_crawl_info:
            return True

        if last_crawl_info['last_modified'] is None:
            return True

        last_checked = last_crawl_info['last_checked']
        if isinstance(last_checked, DateTime):
            last_checked = last_checked.to_native()
        
        if last_checked.tzinfo is not None:
            last_checked = last_checked.replace(tzinfo=None)
        
        now = datetime.now()
        flag = now - last_checked > timedelta(days=7)  
        return flag

    async def crawl(self, start_url, max_pages=None):
        if max_pages is None:
            max_pages = self.config.get('scraper.max_pages')
            
        visited = set()
        to_visit = asyncio.Queue()
        await to_visit.put(start_url)

        await self.initialize()

        try:
            while not to_visit.empty() and len(visited) < max_pages:
                url = await to_visit.get()
                if url not in visited and await self.robots_handler.is_allowed(url) and await self.should_crawl(url):
                    print(f"Crawling: {url}")
                    soup = await self.scrape_website(url)
                    if soup:
                        content_hash = self.get_content_hash(str(soup))
                        if not self.link_manager.content_exists(content_hash):
                            self.link_manager.add_or_update_link(url, content_hash=content_hash, last_modified=datetime.now())
                            internal, external, resources = await self.discover_links(url, soup)
                            visited.add(url)
                            for link in internal:
                                self.link_manager.add_or_update_link(link)
                                if link not in visited:
                                    await to_visit.put(link)
                            
                            parsed_data = self.parser_manager.parse_content(soup)
                            print(f"{url} -----> {parsed_data} <------")
        finally:
            await self.close()

        return visited