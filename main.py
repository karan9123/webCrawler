from neo4j_link_manager import LinkManager
from scraper import Scraper
import asyncio


async def main():
    link_manager = LinkManager()

    scraper = Scraper(link_manager)
    
    start_url = "https://www.imdb.com"  # Replace with desired start URL
    visited_urls = await scraper.crawl(start_url, max_pages=10)
    print(f"Crawled {len(visited_urls)} pages.")
    urls = link_manager.get_urls(1000)
    for url in urls:
        print(url)
    link_manager.close()

if __name__ == "__main__":
    asyncio.run(main())