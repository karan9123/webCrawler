from mongo_link_manager import MongoLinkManager
from scraper import Scraper

def main():
    lm = MongoLinkManager()
    scraper = Scraper()
    prnt_url = ""
    print(prnt_url)
    internal_links, external_links, resources_links = scraper.discover_links(prnt_url)
    for lnk in internal_links:
        lm.add_link(lnk, prnt_url)
    for lnk in external_links:
        lm.add_link(lnk)
    for lnk in resources_links:
        lm.add_link(lnk, prnt_url)

    # to remove links
    # urls = lm.get_urls(1000)
    # for url in urls:
    #     lm.remove_link(url)

    urls = lm.get_urls(1000)
    for url in urls:
        print(url)
    
    lm.close()


if __name__ == "__main__":
    main()