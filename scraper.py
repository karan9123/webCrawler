import json
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from urllib.robotparser import RobotFileParser
# import time
# import random
import logging
import hashlib
from ratelimit import limits, sleep_and_retry
import importlib
from tenacity import retry, stop_after_attempt, wait_exponential
from neo4j.time import DateTime
from datetime import datetime, timedelta, timezone
import asyncio


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)



class Scraper:
    def __init__(self, link_manager, config_manager):
        """
        Initialize the AsyncScraper class.

        :param link_manager: An instance of LinkManager for managing links in the database.
        a link_manager should have definitions for :
            get_last_crawl_info(url: string):
                :param url: The URL to check.
                :return: A dictionary containing last_checked and last_modified dates, or None if not found.
            content_exists(content_hash):
                :param content_hash: The MD5 hash of the page content.
                :return: True if content exists, False otherwise.
            add_or_update_link(url, parent_url, content_hash, lasst_modified):
                :param url: The URL of the link to be added or updated.
                :param parent_url: The URL of the parent link. If not provided, defaults to None.
                :param content_hash: The MD5 hash of the page content. If not provided, defaults to None.
                :param last_modified: The last modified date of the page. If not provided, defaults to None.
        """
        self.config = config_manager
        self.headers = {
            'User-Agent': self.config.get('scraper.headers.user_agent'),
            'Accept': self.config.get('scraper.headers.accept'),
            'Accept-Language': self.config.get('scraper.headers.accept_language'),
            'Accept-Encoding': self.config.get('scraper.headers.accept_encoding'),
            'Connection': self.config.get('scraper.headers.connection'),
            'Upgrade-Insecure-Requests': self.config.get('scraper.headers.upgrade_insecure_requests'),
        }
        
        # self.headers = {
        #     'User-Agent': 'YourBot/1.0 (+http://www.yourwebsite.com/bot.html)',
        #     'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        #     'Accept-Language': 'en-US,en;q=0.5',
        #     'Accept-Encoding': 'gzip, deflate, br',
        #     'Connection': 'keep-alive',
        #     'Upgrade-Insecure-Requests': '1',
        # }
        self.robot_cache_dir = 'robot_cache'
        self.unallowed_links_file = 'unallowed_links.json'
        self.unallowed_links = self.load_unallowed_links()
        self.robot_parsers = {}
        self.link_manager = link_manager
        self.parser_manager = ContentParserManager()

        if not os.path.exists(self.robot_cache_dir):
            os.makedirs(self.robot_cache_dir)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    @sleep_and_retry
    @limits(calls=1, period=5)  # 1 request per 5 seconds
    async def scrape_website(self, url):
        """
        Asynchronously scrape a website.

        :param url: The URL to scrape.
        :return: A BeautifulSoup object of the scraped content, or None if an error occurred.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    response.raise_for_status()
                    content = await response.text()
                    return BeautifulSoup(content, 'html.parser')
        except aiohttp.ClientError as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return None

    async def is_allowed(self, url):
        """
        Check if scraping a URL is allowed by the website's robots.txt file.

        :param url: The URL to check.
        :return: True if scraping is allowed, False otherwise.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        if domain not in self.robot_parsers:
            await self.load_robot_parser(domain)

        is_allowed = self.robot_parsers[domain].can_fetch(self.headers['User-Agent'], url)

        if not is_allowed:
            self.add_unallowed_link(url)
        return is_allowed

    async def load_robot_parser(self, domain):
        """
        Load the robots.txt file for a given domain and create a RobotFileParser object.

        :param domain: The domain to load the robots.txt file for.
        """
        robot_file_path = os.path.join(self.robot_cache_dir, f"{domain}_robots.txt")

        if not os.path.exists(robot_file_path) or self.is_file_outdated(robot_file_path):
            await self.update_robot_file(domain, robot_file_path)

        rp = RobotFileParser()
        rp.parse(self.read_robot_file(robot_file_path))
        self.robot_parsers[domain] = rp

    def is_file_outdated(self, file_path):
        """
        Check if a file is older than 7 days.

        :param file_path: The path to the file to check.
        :return: True if the file is outdated, False otherwise.
        """
        return datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path)) > timedelta(days=7)

    async def update_robot_file(self, domain, file_path):
        """
        Update the robots.txt file for a given domain.

        :param domain: The domain to update the robots.txt file for.
        :param file_path: The path to save the robots.txt file.
        """
        robot_url = f"https://{domain}/robots.txt"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(robot_url, headers=self.headers, timeout=10) as response:
                    response.raise_for_status()
                    content = await response.text()
                    
                    with open(file_path, 'w') as f:
                        f.write(content)
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching robots.txt for {domain}: {str(e)}")
            open(file_path, 'w').close()

    def read_robot_file(self, file_path):
        """
        Read the contents of a robots.txt file.

        :param file_path: The path to the robots.txt file.
        :return: A list of lines from the robots.txt file.
        """
        with open(file_path, 'r') as f:
            return f.read().splitlines()

    def add_unallowed_link(self, url):
        """
        Add a URL to the list of unallowed links.

        :param url: The URL to add to the unallowed links list.
        """
        if url not in self.unallowed_links:
            self.unallowed_links.append(url)
            self.save_unallowed_links()

    def load_unallowed_links(self):
        """
        Load the list of unallowed links from a file.

        :return: A list of unallowed links.
        """
        try:
            if os.path.exists(self.unallowed_links_file):
                with open(self.unallowed_links_file, 'r') as f:
                    content = f.read()
                    if content.strip():
                        return json.loads(content)
                    else:
                        logger.warning(f"{self.unallowed_links_file} is empty. Initializing with an empty list.")
                        return []
            else:
                logger.warning(f"{self.unallowed_links_file} does not exist. Initializing with an empty list.")
                return []
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {self.unallowed_links_file}: {str(e)}. Initializing with an empty list.")
            return []

    def save_unallowed_links(self):
        """
        Save the list of unallowed links to a file.
        """
        with open(self.unallowed_links_file, 'w') as f:
            json.dump(self.unallowed_links, f)

    async def discover_links(self, url, soup):
        """
        Discover internal, external, and resource links from a BeautifulSoup object.

        :param url: The URL of the page being scraped.
        :param soup: A BeautifulSoup object of the scraped content.
        :return: Three lists containing internal, external, and resource links.
        """
        internal_links = set()
        external_links = set()
        resource_links = set()
        base_domain = urlparse(url).netloc

        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            parsed_url = urlparse(full_url)
            
            if parsed_url.netloc == base_domain:
                if await self.is_allowed(full_url):
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
        """
        Calculate the MD5 hash of the given content.

        :param content: The content to hash.
        :return: The MD5 hash of the content.
        """
        return hashlib.md5(content.encode()).hexdigest()

    async def should_crawl(self, url):
        """
        Determine if a URL should be crawled based on its last crawl information.

        :param url: The URL to check.
        :return: True if the URL should be crawled, False otherwise.
        """
        last_crawl_info = self.link_manager.get_last_crawl_info(url)
        if not last_crawl_info:
            return True
        
        # async with aiohttp.ClientSession() as session:
        #     async with session.head(url, headers=self.headers) as response:
        #         headers = response.headers
        #         if 'Last-Modified' in headers:
        #             last_modified = datetime.strptime(headers['Last-Modified'], '%a, %d %b %Y %H:%M:%S GMT')
        #             lst_modified =last_crawl_info['last_modified']
        #             if lst_modified is not None:
        #                 return last_modified > last_crawl_info['last_modified']
        #             else: 
        #                 return True

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

    async def crawl(self, start_url, max_pages=100):
        """
        Asynchronously crawl websites starting from a given URL.

        :param start_url: The URL to start crawling from.
        :param max_pages: The maximum number of pages to crawl.
        :return: A set of visited URLs.
        """
        if max_pages is None:
            max_pages = self.config.get('scraper.max_pages')
            
        visited = set()
        to_visit = asyncio.Queue()
        await to_visit.put(start_url)

        while not to_visit.empty() and len(visited) < max_pages:
            url = await to_visit.get()
            if url not in visited and await self.is_allowed(url) and await self.should_crawl(url):
                logger.info(f"Crawling: {url}")
                soup = await self.scrape_website(url)
                if soup:
                    content_hash = self.get_content_hash(str(soup))
                    if not self.link_manager.content_exists(content_hash):
                        self.link_manager.add_or_update_link(url, content_hash=content_hash, last_modified=datetime.now())
                        internal, external, resources = await self.discover_links(url, soup)
                        visited.add(url)
                        for link in internal:
                            print(f"{url}--->{link}")
                            self.link_manager.add_or_update_link(link)
                            if link not in visited:
                                await to_visit.put(link)
                        
                        # Parse content using the parser manager
                        parsed_data = self.parser_manager.parse_content("default", soup)
                        # Here, we process the parsed_data as needed

        return visited

class ContentParserManager:
    def __init__(self):
        self.parsers = {}

    def load_parser(self, parser_name):
        try:
            module = importlib.import_module(f"parsers.{parser_name}")
            parser_class = getattr(module, f"{parser_name.capitalize()}Parser")
            self.parsers[parser_name] = parser_class()
        except (ImportError, AttributeError) as e:
            logger.error(f"Error loading parser {parser_name}: {str(e)}")
            # Use DefaultParser as fallback
            from parsers.default import DefaultParser
            self.parsers[parser_name] = DefaultParser()

    def parse_content(self, parser_name, content):
        if parser_name not in self.parsers:
            self.load_parser(parser_name)
        return self.parsers[parser_name].parse(content)
    