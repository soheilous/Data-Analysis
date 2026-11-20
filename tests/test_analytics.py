"""Offline tests for project metrics."""
import unittest

from analytics import hashtags, number, project_analytics


def post(code, likes, published, caption='', comments=(), owner='brand', reported=None):
    return {
        'post_url': f'https://www.instagram.com/p/{code}/', 'shortcode': code, 'owner': owner,
        'caption': caption, 'published_at': published, 'total_likes': likes,
        'comments': [{'username': user, 'text': text, 'time': published} for user, text in comments],
        'reported_comment_count': reported, 'likers': [],
    }


class AnalyticsTest(unittest.TestCase):
    def test_number_parses_instagram_forms(self):
        self.assertEqual(number(12), 12)
        self.assertEqual(number('1,204'), 1204)
        self.assertEqual(number('۱۲'), 12)
        self.assertEqual(number('1.2K'), 1200)
        self.assertEqual(number('3M'), 3_000_000)
        self.assertIsNone(number(None))
        self.assertIsNone(number('—'))
        self.assertIsNone(number(True))

    def test_hashtags_support_persian_and_dedupe(self):
        self.assertEqual(hashtags('سلام #کافه_تهران و #Coffee #coffee #نیم‌فاصله'), ['کافه_تهران', 'coffee', 'نیم‌فاصله'])

    def test_empty_project(self):
        result = project_analytics([])
        self.assertEqual(result['summary']['posts'], 0)
        self.assertEqual(result['summary']['avg_engagement'], 0)
        self.assertIsNone(result['summary']['posts_per_week'])
        self.assertEqual(result['top_posts'], [])
        self.assertEqual(len(result['posting']['hours']), 24)

    def test_metrics(self):
        posts = [
            post('A', 100, '2026-11-01T10:00:00+00:00', '#coffee #tehran', [('ali', 'great coffee'), ('sara', 'price?')]),
            post('B', '1.5K', '2026-11-08T10:00:00+00:00', '#coffee', [('ali', 'great again')], reported=40, owner='rival'),
            post('C', None, None, 'no tags'),
        ]
        result = project_analytics(posts)
        summary = result['summary']
        self.assertEqual(summary['posts'], 3)
        self.assertEqual(summary['posts_with_likes'], 2)
        self.assertEqual(summary['total_likes'], 1600)
        self.assertEqual(summary['total_comments'], 42)  # reported count wins over collected
        self.assertEqual(summary['collected_comments'], 3)
        self.assertEqual(summary['unique_commenters'], 2)
        self.assertEqual(summary['avg_likes'], 800)
        self.assertEqual(summary['posts_per_week'], 2)
        self.assertEqual([p['shortcode'] for p in result['top_posts']], ['B', 'A', 'C'])
        self.assertEqual(result['top_posts'][0]['engagement'], 1540)
        self.assertEqual(result['hashtags']['top'][0], {'tag': 'coffee', 'posts': 2, 'avg_engagement': 821.0})
        # 2026-11-01 is a Sunday; its Saturday-start week begins 2026-10-31.
        self.assertEqual(result['posting']['weekly'], [{'week': '2026-10-31', 'posts': 1}, {'week': '2026-11-07', 'posts': 1}])
        self.assertEqual(result['posting']['weekdays'][1]['posts'], 2)
        self.assertEqual(result['posting']['hours'][13]['posts'], 2)  # 10:00 UTC is 13:30 Tehran
        self.assertEqual(result['comments']['top_commenters'][0], {'username': 'ali', 'comments': 2})
        self.assertEqual(result['comments']['top_terms'][0], {'term': 'great', 'count': 2})
        self.assertEqual(result['accounts'][0]['owner'], 'rival')


if __name__ == '__main__':
    unittest.main()
