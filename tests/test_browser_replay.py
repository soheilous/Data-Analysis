"""Run the browser collector in headless Chromium against replayed Instagram fixtures.

Every request is answered from tests/fixtures or aborted, so no Instagram
account or network access is used. The tests are skipped when no Chromium
build is available (run `python -m playwright install chromium`), unless
REQUIRE_BROWSER_TESTS is set.
"""

import os
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from playwright.sync_api import Error, sync_playwright

import browser_scraper
from replay import InstagramReplay, launch_options

POST_PAGES = {'/p/DidbanTest1/': 'post.html'}
CONFIG = {'max_comments': 10, 'likers': False, 'max_likers': 0}


def browser_available():
    # CI sets this so a missing browser fails the run instead of skipping tests.
    if os.environ.get('REQUIRE_BROWSER_TESTS'):
        return True
    try:
        with sync_playwright() as playwright:
            playwright.chromium.launch(**launch_options()).close()
        return True
    except Error:
        return False


@unittest.skipUnless(browser_available(), 'Chromium for Playwright is not installed')
class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(**launch_options())
        self.addCleanup(self.browser.close)

    def page(self, replay):
        context = self.browser.new_context(locale='en-US', viewport={'width': 1366, 'height': 768})
        self.addCleanup(context.close)
        replay.attach(context)
        return context.new_page()

    def test_find_post_links_on_profile(self):
        replay = InstagramReplay({'/example_brand/': 'profile.html'})
        links = browser_scraper.find_post_links(self.page(replay), 'profile', 'example_brand', 5, 0)
        self.assertEqual(links, {
            'DidbanTest1': 'https://www.instagram.com/p/DidbanTest1/',
            'DidbanReel2': 'https://www.instagram.com/reel/DidbanReel2/',
        })

    def test_find_post_links_respects_limit(self):
        replay = InstagramReplay({'/example_brand/': 'profile.html'})
        links = browser_scraper.find_post_links(self.page(replay), 'profile', 'example_brand', 1, 0)
        self.assertEqual(list(links), ['DidbanTest1'])

    def test_read_post_merges_network_and_page_comments(self):
        replay = InstagramReplay(POST_PAGES, ['post_graphql'])
        logs = []
        row = browser_scraper.read_post(
            self.page(replay), 'DidbanTest1', 'https://www.instagram.com/p/DidbanTest1/', CONFIG, logs.append,
        )
        self.assertEqual(row['collection_method'], 'browser_network')
        self.assertEqual(row['media_id'], '4079537413632478069')
        self.assertEqual(row['owner'], 'example_brand')
        self.assertEqual(row['caption'], 'معرفی محصول جدید #اسنوا #didban')
        self.assertEqual(row['published_at'], '2026-11-01T09:30:00+00:00')
        self.assertEqual(row['total_likes'], 1532)
        self.assertEqual(
            [(c['username'], c['text']) for c in row['comments']],
            [('first_fan', 'عالیه 👏'),
             ('example_brand', '@first_fan ممنون از شما'),
             ('second.fan', 'Price?'),
             ('dom_only', 'Only rendered in the page')],
        )
        self.assertEqual(logs, [])
        self.assertEqual(replay.unmatched, [])

    def test_read_post_with_required_tag_missing_returns_none(self):
        replay = InstagramReplay(POST_PAGES, ['post_graphql'])
        row = browser_scraper.read_post(
            self.page(replay), 'DidbanTest1', 'https://www.instagram.com/p/DidbanTest1/', CONFIG, print,
            required_tags={'absent'},
        )
        self.assertIsNone(row)

    def test_read_post_without_network_falls_back_to_page(self):
        replay = InstagramReplay(POST_PAGES)  # API calls are aborted
        logs = []
        row = browser_scraper.read_post(
            self.page(replay), 'DidbanTest1', 'https://www.instagram.com/p/DidbanTest1/', CONFIG, logs.append,
        )
        self.assertEqual(row['collection_method'], 'browser')
        self.assertEqual(row['caption'], 'معرفی محصول جدید #اسنوا #didban')
        self.assertEqual(row['owner'], 'example_brand')
        self.assertEqual(row['total_likes'], 1532)  # from og:description
        self.assertEqual([c['username'] for c in row['comments']], ['first_fan', 'dom_only'])
        self.assertEqual(row['comments'][0]['comment_id'], '18000000000000001')

    def test_blocked_api_response_stops_read(self):
        replay = InstagramReplay(POST_PAGES, ['post_graphql'])
        replay.exchanges[0] = dict(replay.exchanges[0], status=429)
        with self.assertRaises(browser_scraper.CollectionError):
            browser_scraper.read_post(
                self.page(replay), 'DidbanTest1', 'https://www.instagram.com/p/DidbanTest1/', CONFIG, print,
            )

    def test_missing_post_page_is_rejected(self):
        replay = InstagramReplay(POST_PAGES)
        page = self.page(replay)
        page.route('https://www.instagram.com/p/Missing/', lambda route: route.fulfill(
            status=404, content_type='text/html', body='<p>Sorry, this page isn&#39;t available.</p>'))
        with self.assertRaises(browser_scraper.CollectionError):
            browser_scraper.read_post(page, 'Missing', 'https://www.instagram.com/p/Missing/', CONFIG, print)


@unittest.skipUnless(browser_available(), 'Chromium for Playwright is not installed')
class CollectInBrowserTests(unittest.TestCase):
    """Drive collect_in_browser end to end with a replayed, signed-in session."""

    def run_collection(self, config, known_posts=()):
        replay = InstagramReplay(
            {'/': 'home.html', '/example_brand/': 'profile.html', **POST_PAGES}, ['post_graphql'],
        )
        # Start the Playwright driver before LOCALAPPDATA is redirected: on
        # Windows the driver finds its installed browsers through LOCALAPPDATA.
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        real_launch = playwright.chromium.launch_persistent_context

        def launch_persistent_context(user_data_dir, **options):
            options.pop('channel', None)
            context = real_launch(user_data_dir, **{**options, **launch_options()})
            replay.attach(context)
            return context

        @contextmanager
        def replayed_playwright():
            yield SimpleNamespace(chromium=SimpleNamespace(
                launch_persistent_context=launch_persistent_context))

        rows, logs = [], []
        with tempfile.TemporaryDirectory() as local_app_data, \
                patch.dict(os.environ, {'LOCALAPPDATA': local_app_data}), \
                patch.object(browser_scraper, 'sync_playwright', replayed_playwright):
            try:
                browser_scraper.collect_in_browser(config, rows.append, logs.append, known_posts)
            except browser_scraper.CollectionError as error:
                # collect_in_browser hides Playwright errors from users; show them here.
                if isinstance(error.__context__, Error):
                    raise AssertionError(f'Playwright error: {error.__context__}') from error
                raise
        return rows, logs

    def test_profile_collection_saves_post_and_skips_known(self):
        config = {
            'profiles': ['example_brand'], 'hashtags': [], 'max_posts': 5, 'scrolls': 0,
            'max_comments': 10, 'max_likers': 0, 'likers': False, 'background': True,
        }
        rows, logs = self.run_collection(config, known_posts={'DidbanReel2'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['shortcode'], 'DidbanTest1')
        self.assertEqual(rows[0]['source'], 'example_brand')
        self.assertEqual(rows[0]['source_type'], 'profile')
        self.assertEqual(rows[0]['total_likes'], 1532)
        self.assertIn('1 پست قبلاً ثبت شده بود و دوباره باز نشد.', logs)

    def profile_tags_config(self, tag):
        return {
            'profiles': ['example_brand'], 'hashtags': [tag], 'collection_scope': 'profile_tags',
            'max_posts': 1, 'scrolls': 0, 'max_comments': 10, 'max_likers': 0, 'likers': False,
            'background': True,
        }

    def test_profile_tags_scope_keeps_post_with_tag(self):
        rows, _ = self.run_collection(self.profile_tags_config('اسنوا'))
        self.assertEqual([row['shortcode'] for row in rows], ['DidbanTest1'])

    def test_profile_tags_scope_without_match_reports_it(self):
        with self.assertRaises(browser_scraper.CollectionError) as caught:
            self.run_collection(self.profile_tags_config('ناموجود'))
        self.assertIn('کپشنی با تگ', str(caught.exception))

if __name__ == '__main__':
    unittest.main()
