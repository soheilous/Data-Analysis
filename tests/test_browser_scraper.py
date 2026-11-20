"""Offline tests for browser_scraper helpers that need no browser."""

import os
os.environ.setdefault('DIDBAN_PAUSE_SCALE', '0')  # no human-scale waits in tests

import unittest
from unittest.mock import Mock

from browser_scraper import (
    check_page_access, matches_source, matching_caption, normalized_tag, parse_post_url,
)
from direct_scraper import CollectionError
from instagram_network import PostResponses


class ParsePostUrlTests(unittest.TestCase):
    def test_accepted_forms(self):
        cases = {
            'https://www.instagram.com/p/DidbanTest1/': ('DidbanTest1', 'https://www.instagram.com/p/DidbanTest1/'),
            ' https://instagram.com/p/Abc-_9 ': ('Abc-_9', 'https://www.instagram.com/p/Abc-_9/'),
            'https://www.instagram.com/reel/R1/?igsh=x': ('R1', 'https://www.instagram.com/reel/R1/'),
            'https://WWW.INSTAGRAM.COM/reels/R2/': ('R2', 'https://www.instagram.com/reel/R2/'),
        }
        for value, expected in cases.items():
            with self.subTest(value):
                self.assertEqual(parse_post_url(value), expected)

    def test_rejected_forms(self):
        for value in (
            'http://www.instagram.com/p/Abc/',
            'https://evil.example/p/Abc/',
            'https://www.instagram.com.evil.example/p/Abc/',
            'https://www.instagram.com/example_brand/',
            'https://www.instagram.com/p/Abc/extra/',
            'https://www.instagram.com/p/' + 'a' * 33 + '/',
            'DidbanTest1',
        ):
            with self.subTest(value), self.assertRaises(ValueError):
                parse_post_url(value)


class MatchesSourceTests(unittest.TestCase):
    def test_profile(self):
        self.assertTrue(matches_source('https://www.instagram.com/Example_Brand/', 'profile', 'example_brand'))
        self.assertFalse(matches_source('https://www.instagram.com/accounts/login/?next=/example_brand/',
                                        'profile', 'example_brand'))
        self.assertFalse(matches_source('https://instagram.com/example_brand/', 'profile', 'example_brand'))

    def test_hashtag_page_and_keyword_search(self):
        self.assertTrue(matches_source('https://www.instagram.com/explore/tags/%D8%A7%D8%B3%D9%86%D9%88%D8%A7/',
                                       'hashtag', 'اسنوا'))
        self.assertTrue(matches_source('https://www.instagram.com/explore/search/keyword/?q=%23Didban',
                                       'hashtag', 'didban'))
        self.assertFalse(matches_source('https://www.instagram.com/explore/search/keyword/?q=didban',
                                        'hashtag', 'didban'))
        self.assertFalse(matches_source('https://www.instagram.com/explore/', 'hashtag', 'didban'))


class CaptionTests(unittest.TestCase):
    def page(self, caption):
        page = Mock()
        page.evaluate.return_value = {'caption': caption, 'owner': None}
        return page

    def test_network_caption_wins_when_it_has_the_tag(self):
        page = self.page('page caption #didban')
        self.assertEqual(matching_caption(page, 'network #Didban', {'didban'}), 'network #Didban')

    def test_tags_are_normalized(self):
        # A full-width hash sign counts as a tag marker, and case is folded.
        caption = 'متن ＃اسنوا'
        self.assertEqual(matching_caption(self.page(None), caption, {normalized_tag('اسنوا')}), caption)
        self.assertEqual(normalized_tag('DIDBAN'), 'didban')

    def test_tag_inside_word_or_missing_returns_none(self):
        self.assertIsNone(matching_caption(self.page('word#didban'), 'no tags here', {'didban'}))
        self.assertIsNone(matching_caption(self.page(None), None, {'didban'}))


class PageAccessTests(unittest.TestCase):
    def test_challenge_and_login_paths_stop_collection(self):
        for path in ('/challenge/x/', '/checkpoint/', '/accounts/login/', '/accounts/suspended/'):
            with self.subTest(path), self.assertRaises(CollectionError):
                check_page_access(Mock(url='https://www.instagram.com' + path), PostResponses('', 0))

    def test_blocked_network_stops_collection(self):
        network = PostResponses('', 0)
        network.blocked = True
        with self.assertRaises(CollectionError):
            check_page_access(Mock(url='https://www.instagram.com/p/DidbanTest1/'), network)

    def test_normal_page_passes(self):
        check_page_access(Mock(url='https://www.instagram.com/p/DidbanTest1/'), PostResponses('', 0))


if __name__ == '__main__':
    unittest.main()
