"""Replay recorded Instagram responses without network access.

Fixtures live in tests/fixtures. Each file under fixtures/instagram holds a
list of exchanges (method, url, post_data, resource_type, status, headers,
body). The same exchanges feed two kinds of tests:

* FakeResponse objects for fast unit tests of instagram_network.PostResponses.
* Playwright routes, so a real headless Chromium loads fixture pages and
  receives fixture API responses from https://www.instagram.com. Any request
  without a fixture is aborted, so tests never reach the network.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

FIXTURES = Path(__file__).parent / 'fixtures'


def load_exchanges(name):
    return json.loads((FIXTURES / 'instagram' / f'{name}.json').read_text(encoding='utf-8'))['exchanges']


def body_text(exchange):
    body = exchange['body']
    return body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)


class FakeResponse:
    """The parts of playwright.sync_api.Response that PostResponses reads."""

    def __init__(self, exchange):
        self.url = exchange['url']
        self.status = exchange['status']
        self.headers = exchange.get('headers', {})
        self.request = SimpleNamespace(
            resource_type=exchange.get('resource_type', 'fetch'),
            post_data=exchange.get('post_data'),
        )
        self._text = body_text(exchange)

    def text(self):
        return self._text


def fake_responses(name):
    return [FakeResponse(exchange) for exchange in load_exchanges(name)]


class InstagramReplay:
    """Serve fixture pages and API exchanges to a Playwright context."""

    def __init__(self, pages, exchange_files=()):
        self.pages = {path: (FIXTURES / 'pages' / file).read_text(encoding='utf-8')
                      for path, file in pages.items()}
        self.exchanges = [exchange for name in exchange_files for exchange in load_exchanges(name)]
        self.unmatched = []

    def attach(self, context):
        context.route('**/*', self.handle)

    def handle(self, route):
        request = route.request
        url = request.url
        for exchange in self.exchanges:
            if (exchange['method'] == request.method and exchange['url'] == url
                    and exchange.get('post_data') in (None, request.post_data)):
                return route.fulfill(
                    status=exchange['status'], headers=exchange.get('headers', {}), body=body_text(exchange),
                )
        if request.resource_type == 'document' and url.startswith('https://www.instagram.com/'):
            path = url.removeprefix('https://www.instagram.com').split('?')[0]
            if path in self.pages:
                return route.fulfill(status=200, content_type='text/html; charset=utf-8', body=self.pages[path])
        self.unmatched.append(url)
        return route.abort()


def chromium_executable():
    """Optional override when Playwright's own browser build is not installed."""
    return os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or None


def launch_options():
    """Browser options for replay tests.

    Routes answer or abort every request, but a few browser-internal requests
    (for example redirects of fulfilled navigations) can bypass routing. The
    unreachable proxy makes sure those fail instead of reaching the internet.
    """
    return {'executable_path': chromium_executable(), 'proxy': {'server': 'http://127.0.0.1:9'}}
