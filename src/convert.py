import argparse
import sys
import typing
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


@dataclass
class Token:
    position: typing.Tuple[int, int]
    key: str
    value: str


class MyHTMLParser(HTMLParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.updates = []
        self.path = self.tag = self.i18n_token = None

    def convert(self, path):
        self.path = path
        self.tag = ''.join(map(str.capitalize, path.stem.split(".")[:-1]))
        self.updates = []
        with open(self.path) as f:
            s = f.read()
        self.feed(s)
        ss = s.splitlines()
        for pos, n, new in self.updates[::-1]:
            l, i = pos
            ss[l] = ss[l][:i] + new + ss[l][i+n:]
        with open(self.path, 'w') as f:
            f.write('\n'.join(ss))
        print(self.updates)

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k.startswith('i18n'):
                self.i18n_token = Token(self.getpos(), k, v)

    def handle_data(self, data) -> None:
        if self.i18n_token:
            self.updates.append([
                self.getpos(),
                len(data),
                "{{ '%s.%s' | translate }}" % (
                    self.tag, self.i18n_token.value.split('@')[-1])
            ])
        self.i18n_token = None

    def handle_pi(self, data: str) -> None:
        return super().handle_pi(data)


def convert_file(path: Path):
    paths = [path] if path.is_file() else list(path.rglob('*.html'))
    for html_path in paths:
        parser = MyHTMLParser()
        parser.convert(html_path)


def main():
    parser = argparse.ArgumentParser('i18n-to-ngx')
    parser.add_argument('src', type=Path)
    args = parser.parse_args(sys.argv[1:])
    convert_file(args.src)
