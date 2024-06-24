from neo4j import GraphDatabase
from urllib.parse import urlparse
from datetime import datetime

class LinkManager:
    def __init__(self, uri="bolt://localhost:7687", user="neo4j", password="password", database="crawler"):
        """
        Initializes a Neo4jLinkManager instance.

        :param uri: The URI of the Neo4j database. Defaults to "bolt://localhost:7687".
        :param user: The username for the Neo4j database. Defaults to "neo4j".
        :param password: The password for the Neo4j database.
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        """
        Closes the Neo4j driver connection.
        """
        self.driver.close()

    def add_link(self, url, parent_url=None):
        """
        Adds a new link to the database, or updates an existing link with new information.

        :param url: The URL of the link to be added or updated.
        :param parent_url: The URL of the parent link. If not provided, defaults to None.
        """
        domain = urlparse(url).netloc
        with self.driver.session() as session:
            session.execute_write(self._create_or_update_link, url, domain, parent_url)

    @staticmethod
    def _create_or_update_link(tx, url, domain, parent_url):
        # Create or update the link
        query = (
            "MERGE (l:Link {url: $url}) "
            "SET l.domain = $domain, l.lastChecked = datetime() "
            "RETURN l"
        )
        result = tx.run(query, url=url, domain=domain)
        link = result.single()['l']

        # If parent_url is provided, create the relationship
        if parent_url:
            query = (
                "MATCH (l:Link {url: $url}) "
                "MERGE (p:Link {url: $parent_url}) "
                "MERGE (p)-[:LINKS_TO]->(l)"
            )
            tx.run(query, url=url, parent_url=parent_url)

        return link

    def remove_link(self, url):
        """
        Removes a link from the database and updates its relationships.

        :param url: The URL of the link to be removed.
        """
        with self.driver.session() as session:
            session.write_transaction(self._remove_link, url)

    @staticmethod
    def _remove_link(tx, url):
        query = (
            "MATCH (l:Link {url: $url}) "
            "OPTIONAL MATCH (l)-[:LINKS_TO]->(child) "
            "OPTIONAL MATCH (parent)-[:LINKS_TO]->(l) "
            "FOREACH (p IN CASE WHEN parent IS NOT NULL THEN [parent] ELSE [] END | "
            "  FOREACH (c IN CASE WHEN child IS NOT NULL THEN [child] ELSE [] END | "
            "    MERGE (p)-[:LINKS_TO]->(c))) "
            "DETACH DELETE l"
        )
        tx.run(query, url=url)

    def get_children(self, url):
        """
        Retrieves the child URLs associated with a given parent URL.

        :param url: The URL of the parent link.
        :return: A list of child URLs associated with the given parent URL.
        """
        with self.driver.session() as session:
            return session.read_transaction(self._get_children, url)

    @staticmethod
    def _get_children(tx, url):
        query = (
            "MATCH (l:Link {url: $url})-[:LINKS_TO]->(child) "
            "RETURN child.url"
        )
        result = tx.run(query, url=url)
        return [record["child.url"] for record in result]

    def get_parent(self, url):
        """
        Retrieves the parent URL of a given URL.

        :param url: The URL of the child link.
        :return: The parent URL if it exists, otherwise None.
        """
        with self.driver.session() as session:
            return session.read_transaction(self._get_parent, url)

    @staticmethod
    def _get_parent(tx, url):
        query = (
            "MATCH (parent)-[:LINKS_TO]->(l:Link {url: $url}) "
            "RETURN parent.url"
        )
        result = tx.run(query, url=url)
        record = result.single()
        return record["parent.url"] if record else None

    def get_links_by_domain(self, domain):
        """
        Retrieves all links for a given domain.

        :param domain: The domain name to search for.
        :return: A list of URLs associated with the given domain.
        """
        with self.driver.session() as session:
            return session.read_transaction(self._get_links_by_domain, domain)

    @staticmethod
    def _get_links_by_domain(tx, domain):
        query = (
            "MATCH (l:Link {domain: $domain}) "
            "RETURN l.url"
        )
        result = tx.run(query, domain=domain)
        return [record["l.url"] for record in result]

    def update_last_checked(self, url):
        """
        Updates the lastChecked timestamp for a given URL.

        :param url: The URL to update.
        """
        with self.driver.session() as session:
            session.write_transaction(self._update_last_checked, url)

    @staticmethod
    def _update_last_checked(tx, url):
        query = (
            "MATCH (l:Link {url: $url}) "
            "SET l.lastChecked = datetime()"
        )
        tx.run(query, url=url)

    def get_links_to_check(self, time_threshold):
        """
        Retrieves links that haven't been checked since the given time threshold.

        :param time_threshold: A datetime object representing the threshold.
        :return: A list of URLs that need to be checked.
        """
        with self.driver.session() as session:
            return session.read_transaction(self._get_links_to_check, time_threshold)

    @staticmethod
    def _get_links_to_check(tx, time_threshold):
        query = (
            "MATCH (l:Link) "
            "WHERE l.lastChecked < datetime($threshold) "
            "RETURN l.url"
        )
        result = tx.run(query, threshold=time_threshold.isoformat())
        return [record["l.url"] for record in result]

    def get_urls(self, num_links):
        """
        Returns a specified number of links from the database.

        :param num_links: The number of links to return.
        :return: A list of link URLs.
        """
        with self.driver.session() as session:
            return session.execute_read(self._get_urls, num_links)

    @staticmethod
    def _get_urls(tx, num_links):
        query = (
            "MATCH (l:Link) "
            "RETURN l.url "
            "LIMIT $num_links"
        )
        result = tx.run(query, num_links=num_links)
        return [record["l.url"] for record in result]

    def delete_links_by_domain(self, domain):
        """
        Deletes all links of a given domain name.

        :param domain: The domain name of the links to be deleted.
        :return: The number of links deleted.
        """
        with self.driver.session() as session:
            return session.write_transaction(self._delete_links_by_domain, domain)

    @staticmethod
    def _delete_links_by_domain(tx, domain):
        query = (
            "MATCH (l:Link {domain: $domain}) "
            "WITH l, size((l)-[:LINKS_TO]->()) as num_deleted "
            "DETACH DELETE l "
            "RETURN sum(num_deleted) as total_deleted"
        )
        result = tx.run(query, domain=domain)
        return result.single()["total_deleted"]

def test_main():
    lm = LinkManager()
    print('Testing Neo4j')
    # lm.add_link('https://www.imdb.com/title/tt0111161/')
    # # print(lm.delete_links_by_domain('www.imdb.com'))
    k = lm.get_urls(100)
    for urls in k:
        print(urls)
    lm.close()

if __name__ == '__main__':
    test_main()