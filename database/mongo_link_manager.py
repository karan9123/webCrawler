from pymongo import MongoClient
from urllib.parse import urlparse
from datetime import datetime


class MongoLinkManager:
    def __init__(self, db_name='web_scraper'):
        """
        Initializes a MongoLinkManager instance.

        :param db_name: The name of the MongoDB database to use. Defaults to 'web_scraper'.
        """

        # Create a synchronous client
        self.client = MongoClient('mongodb://127.0.0.1:27017/')
        self.db = self.client[db_name]
        self.links = self.db.links
        self.link_children = self.db.linkChildren
        
        # Create indexes on the 'links' and 'linkChildren' collections
        # 'url' and 'domain' fields are indexed for efficient searching
        # 'lastChecked' field is indexed for efficient retrieval of links to check
        # 'parentUrl' and 'childUrl' fields are indexed for efficient parent-child relationship management
        self.links.create_index('url', unique=True)
        self.links.create_index('domain')
        self.links.create_index('lastChecked')
        self.link_children.create_index('parentUrl')
        self.link_children.create_index('childUrl')

    def add_link(self, url, parent_url=None):
        """
        Adds a new link to the database, or updates an existing link with new information.

        :param url: The URL of the link to be added or updated.
        :type url: str
        :param parent_url: The URL of the parent link. If not provided, defaults to None.
        :type parent_url: str, optional

        :return: None
        """
        domain = urlparse(url).netloc
        link_doc = {
            'url': url,
            'domain': domain,
            'parent': parent_url,
            'lastChecked': datetime.now()
        }
        
        # Update or insert the link document
        # If the link already exists, the '$set' operation will update the existing fields
        # If the link does not exist, the upsert=True option will insert a new document
        self.links.update_one({'url': url}, {'$set': link_doc}, upsert=True)
        
        # Update parent's children list
        # If a parent URL is provided, insert a new document into the 'linkChildren' collection
        # This document represents the parent-child relationship between the parent and child links
        if parent_url:
            self.link_children.insert_one({
                'parentUrl': parent_url,
                'childUrl': url
            })

    def remove_link(self, url):
        """
        Removes a link from the database and updates its parent-child relationships.

        :param url: The URL of the link to be removed.
        :type url: str

        :return: None
        """
        # Remove the link
        self.links.delete_one({'url': url})

        # Remove parent-child relationships
        self.link_children.delete_many({'childUrl': url})

        # Update children's parent
        children = self.get_children(url)
        parent = self.get_parent(url)
        for child in children:
            if parent:
                self.link_children.update_one(
                    {'childUrl': child},
                    {'$set': {'parentUrl': parent}}
                )
            else:
                self.link_children.delete_one({'childUrl': child})

    def get_children(self, url):
        """
        Retrieves the child URLs associated with a given parent URL.

        :param url: The URL of the parent link.
        :type url: str
        :return: A list of child URLs associated with the given parent URL.
        :rtype: list

        This method uses the 'find' method of the 'linkChildren' collection to query for documents
        where the 'parentUrl' field matches the provided URL. It then extracts the 'childUrl' field
        from each matching document and returns them as a list.
        """
        children = self.link_children.find({'parentUrl': url})
        return [child['childUrl'] for child in children]

    def get_parent(self, url):
        link = self.links.find_one({'url': url})
        return link['parent'] if link else None

    def get_links_by_domain(self, domain):
        return [link['url'] for link in self.links.find({'domain': domain})]

    def update_last_checked(self, url):
        self.links.update_one({'url': url}, {'$set': {'lastChecked': datetime.now()}})

    def get_links_to_check(self, time_threshold):
        return [link['url'] for link in self.links.find({'lastChecked': {'$lt': time_threshold}})]


    def get_urls(self, num_links):
        """
        Returns a specified number of links from the database.
        
        :param num_links: The number of links to return
        :return: A list of link URLs
        """
        return [link['url'] for link in self.links.find().limit(num_links)]
    def delete_links_by_domain(self, domain):
        """
        Deletes all links of a given domain name.
        
        :param domain: The domain name of the links to be deleted
        :return: The number of links deleted
        """
        # Get all links for the given domain
        links_to_delete = self.get_links_by_domain(domain)
        
        # Remove each link
        for url in links_to_delete:
            self.remove_link(url)
        
        # Delete all links with the given domain
        result = self.links.delete_many({'domain': domain})
        
        # Return the number of deleted links
        return result.deleted_count
    
    
    def close(self):
        self.client.close()



def test_main():
    lm = MongoLinkManager()
    print('Testing Mongo')
    print(lm.delete_links_by_domain('www.imdb.com'))
    k = lm.get_urls(100)
    for urls in k:
        print(urls)
    lm.close()



if __name__ == '__main__':
    test_main()