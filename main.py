from neo4j_link_manager import LinkManager
from scraper import Scraper
import asyncio
from config_manager import ConfigManager


async def main():

    config_manager = ConfigManager()
    link_manager = LinkManager(config_manager)

    scraper = Scraper(link_manager, config_manager)
    start_url = "https://www.gutenberg.org"  # Replace with desired start URL
    visited_urls = await scraper.crawl(start_url, max_pages=10)
    print(f"Crawled {len(visited_urls)} pages.")
    
    # urls = link_manager.get_urls(1000)
    # for url in urls:
    #     link_manager.remove_link(url)
    # urls = link_manager.get_urls(1000)
    # for url in urls:
    #     print(url)




    link_manager.close()

if __name__ == "__main__":
    asyncio.run(main())