import importlib
from parsers.default_parser import DefaultParser

class ParserManager:
    def __init__(self):
        self.parsers = {
            'default': DefaultParser(),
        }

    def load_parser(self, parser_name):
        if parser_name not in self.parsers:
            try:
                module = importlib.import_module(f"parsers.custom_parsers.{parser_name}")
                parser_class = getattr(module, f"{parser_name.capitalize()}Parser")
                self.parsers[parser_name] = parser_class()
            except (ImportError, AttributeError) as e:
                print(f"Error loading parser {parser_name}: {str(e)}")
                self.parsers[parser_name] = DefaultParser()

    def parse_content(self, content, parser_name="default"):
        if parser_name not in self.parsers:
            self.load_parser(parser_name)
        return self.parsers[parser_name].parse(content)