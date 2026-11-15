import unittest
from unittest.mock import Mock

from browser_scraper import find_post_links, matching_caption


class ProfileLinksTests(unittest.TestCase):
    def test_profile_prefixed_reel_links_are_normalized(self):
        page = Mock()
        page.url = 'https://www.instagram.com/example/'
        page.goto.return_value.status = 200
        page.locator.return_value.evaluate_all.return_value = [
            'https://www.instagram.com/example/reel/ABC_123/',
            'https://www.instagram.com/p/XYZ456/',
        ]
        links = find_post_links(page, 'profile', 'example', 2, 0)
        self.assertEqual(links, {
            'ABC_123': 'https://www.instagram.com/reel/ABC_123/',
            'XYZ456': 'https://www.instagram.com/p/XYZ456/',
        })

    def test_matching_caption_uses_page_when_network_caption_empty(self):
        page = Mock()
        page.evaluate.return_value = {'caption': 'متن پست #اسنوا', 'owner': None}
        self.assertEqual(matching_caption(page, '', {'اسنوا'}), 'متن پست #اسنوا')


if __name__ == '__main__':
    unittest.main()
