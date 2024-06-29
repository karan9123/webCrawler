class DefaultParser:
    def parse(self, content):
        # Implement default parsing logic
        # For now, let's return a simple dictionary
        return {
            'title': content.title.string if content.title else 'No title',
            'text': content.get_text()[:100] + '...'  # First 100 characters of text
        }