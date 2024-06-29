from bs4 import BeautifulSoup
import re

class CleanTextParser:
    def parse(self, content):
        if isinstance(content, BeautifulSoup):
            # If content is already a BeautifulSoup object, use it directly
            soup = content
        else:
            # If content is a string, create a BeautifulSoup object
            soup = BeautifulSoup(content, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        
        # Get text
        text = soup.get_text()
        
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return {
            'title': soup.title.string if soup.title else 'No title',
            'content': text
        }