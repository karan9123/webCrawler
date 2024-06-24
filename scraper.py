import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
from urllib.robotparser import RobotFileParser
from datetime import datetime, timedelta
import json
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class Scraper:
    def __init__(self):
        """
        Initialize the Scraper class.

        Attributes:
        headers (dict): Dictionary containing HTTP headers for requests.
        robot_cache_dir (str): Directory path to store robots.txt cache files.
        unallowed_links_file (str): File name to store unallowed links.
        unallowed_links (list): List of unallowed links.
        robot_parsers (dict): Dictionary to store RobotFileParser objects.
        session (requests.Session): Session object for making HTTP requests.

        Returns:
        None
        """

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
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
        self.session = self.create_session()

        if not os.path.exists(self.robot_cache_dir):
            os.makedirs(self.robot_cache_dir)

    def create_session(self):
        session = requests.Session()
        retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def scrape_website(self, url):
        try:
            response = self.session.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            return soup
        except requests.RequestException as e:
            print(f"Error scraping {url}: {str(e)}")
            return None

    def is_allowed(self, url):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        if domain not in self.robot_parsers:
            self.load_robot_parser(domain)

        is_allowed = self.robot_parsers[domain].can_fetch(self.headers['User-Agent'], url)

        if not is_allowed:
            self.add_unallowed_link(url)

        return is_allowed

    def load_robot_parser(self, domain):
        robot_file_path = os.path.join(self.robot_cache_dir, f"{domain}_robots.txt")

        if not os.path.exists(robot_file_path) or self.is_file_outdated(robot_file_path):
            self.update_robot_file(domain, robot_file_path)

        rp = RobotFileParser()
        rp.parse(self.read_robot_file(robot_file_path))
        self.robot_parsers[domain] = rp

    def is_file_outdated(self, file_path):
        return datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path)) > timedelta(days=7)

    def update_robot_file(self, domain, file_path):
        robot_url = f"https://{domain}/robots.txt"
        try:
            response = self.session.get(robot_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            with open(file_path, 'w') as f:
                f.write(response.text)
        except requests.RequestException as e:
            print(f"Error fetching robots.txt for {domain}: {str(e)}")
            open(file_path, 'w').close()

    def read_robot_file(self, file_path):
        with open(file_path, 'r') as f:
            return f.read().splitlines()

    def add_unallowed_link(self, url):
        if url not in self.unallowed_links:
            self.unallowed_links.append(url)
            self.save_unallowed_links()

    def load_unallowed_links(self):
        try:
            if os.path.exists(self.unallowed_links_file):
                with open(self.unallowed_links_file, 'r') as f:
                    content = f.read()
                    if content.strip():  # Check if file is not empty
                        return json.loads(content)
                    else:
                        print(f"Warning: {self.unallowed_links_file} is empty. Initializing with an empty list.")
                        return []
            else:
                print(f"Warning: {self.unallowed_links_file} does not exist. Initializing with an empty list.")
                return []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from {self.unallowed_links_file}: {str(e)}. Initializing with an empty list.")
            return []

    def save_unallowed_links(self):
        with open(self.unallowed_links_file, 'w') as f:
            json.dump(self.unallowed_links, f)

    def discover_links(self, url):
        soup = self.scrape_website(url)
        if not soup:
            return [], [], []
        internal_links = set()
        external_links = set()
        resource_links = set()
        base_domain = urlparse(url).netloc
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            parsed_url = urlparse(full_url)
            
            if parsed_url.netloc == base_domain:
                if self.is_allowed(full_url):
                    internal_links.add(full_url)
            elif parsed_url.scheme in ['http', 'https']:
                external_links.add(full_url)
        for tag in soup.find_all(['img', 'script', 'link']):
            src = tag.get('src') or tag.get('href')
            if src:
                full_url = urljoin(url, src)
                resource_links.add(full_url)
        
        # Implement rate limiting
        time.sleep(random.uniform(1, 3))
        
        return list(internal_links), list(external_links), list(resource_links)

    def crawl(self, start_url, max_pages=100):
        visited = set()
        to_visit = [start_url]
        
        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url not in visited and self.is_allowed(url):
                print(f"Crawling: {url}")
                internal, external, resources = self.discover_links(url)
                visited.add(url)
                to_visit.extend([link for link in internal if link not in visited])
        
        return visited