import aiohttp
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
import os
from datetime import datetime, timedelta

class RobotsHandler:
    def __init__(self, headers):
        self.headers = headers
        self.robot_cache_dir = 'robot_cache'
        self.robot_parsers = {}

        if not os.path.exists(self.robot_cache_dir):
            os.makedirs(self.robot_cache_dir)

    async def is_allowed(self, url):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        if domain not in self.robot_parsers:
            await self.load_robot_parser(domain)

        return self.robot_parsers[domain].can_fetch(self.headers['User-Agent'], url)

    async def load_robot_parser(self, domain):
        robot_file_path = os.path.join(self.robot_cache_dir, f"{domain}_robots.txt")

        if not os.path.exists(robot_file_path) or self.is_file_outdated(robot_file_path):
            await self.update_robot_file(domain, robot_file_path)

        rp = RobotFileParser()
        rp.parse(self.read_robot_file(robot_file_path))
        self.robot_parsers[domain] = rp

    def is_file_outdated(self, file_path):
        return datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path)) > timedelta(days=7)

    async def update_robot_file(self, domain, file_path):
        robot_url = f"https://{domain}/robots.txt"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(robot_url, headers=self.headers, timeout=10) as response:
                    response.raise_for_status()
                    content = await response.text()
                    
                    with open(file_path, 'w') as f:
                        f.write(content)
        except aiohttp.ClientError as e:
            print(f"Error fetching robots.txt for {domain}: {str(e)}")
            open(file_path, 'w').close()

    def read_robot_file(self, file_path):
        with open(file_path, 'r') as f:
            return f.read().splitlines()