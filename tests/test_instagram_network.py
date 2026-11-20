"""Offline tests for instagram_network.PostResponses using recorded response fixtures."""

import os
os.environ.setdefault('DIDBAN_PAUSE_SCALE', '0')  # no human-scale waits in tests

import unittest

from playwright.sync_api import Error

from direct_scraper import CollectionError
from instagram_network import PostResponses, edges, timestamp
from replay import FakeResponse, fake_responses, load_exchanges

SHORTCODE = 'DidbanTest1'
MEDIA_ID = '4079537413632478069'


def feed(responses, *names):
    for name in names:
        for response in fake_responses(name):
            responses.receive(response)
    return responses


class HelperTests(unittest.TestCase):
    def test_timestamp_accepts_unix_seconds_only_in_range(self):
        self.assertEqual(timestamp(1793525400), '2026-11-01T09:30:00+00:00')
        self.assertEqual(timestamp(0), '1970-01-01T00:00:00+00:00')
        for value in (-1, 253402300799, '1793525400', None):
            self.assertIsNone(timestamp(value))

    def test_edges_skips_malformed_entries(self):
        node = {'conn': {'edges': [{'node': {'id': 1}}, {'node': 'x'}, 'bad', {'other': {}}]}}
        self.assertEqual(edges(node, 'conn'), [{'id': 1}])
        self.assertEqual(edges({'conn': None}, 'conn'), [])
        self.assertEqual(edges({'conn': {'edges': None}}, 'conn'), [])

    def test_media_id_is_derived_from_shortcode(self):
        self.assertEqual(PostResponses(SHORTCODE, 5).media_ids, {MEDIA_ID})
        self.assertEqual(PostResponses('', 0).media_ids, set())
        self.assertEqual(PostResponses('not a code!', 0).media_ids, set())


class GraphQLPostTests(unittest.TestCase):
    def test_post_fields_and_threaded_comments(self):
        network = feed(PostResponses(SHORTCODE, 10), 'post_graphql')
        self.assertEqual(network.fields, {
            'media_id': MEDIA_ID,
            'owner': 'example_brand',
            'caption': 'معرفی محصول جدید #اسنوا #didban',
            'published_at': '2026-11-01T09:30:00+00:00',
            'total_likes': 1532,
        })
        self.assertEqual(network.json_responses, 1)
        self.assertEqual(list(network.comments), ['18000000000000001', '18000000000000002', '18000000000000003'])
        first = network.comments['18000000000000001']
        self.assertEqual(first, {
            'comment_id': '18000000000000001', 'text': 'عالیه 👏', 'username': 'first_fan',
            'time': '2026-11-01T10:30:00+00:00', 'likes': None,
        })
        self.assertEqual(network.comments['18000000000000002']['username'], 'example_brand')
        network.check_access()

    def test_comment_limit_counts_replies(self):
        network = feed(PostResponses(SHORTCODE, 2), 'post_graphql')
        self.assertEqual(list(network.comments), ['18000000000000001', '18000000000000002'])

    def test_other_shortcode_is_ignored(self):
        network = feed(PostResponses('OtherPost00', 10), 'post_graphql')
        self.assertEqual(network.fields, {})
        self.assertEqual(network.comments, {})
        self.assertEqual(network.json_responses, 1)

    def test_repeated_response_does_not_duplicate_comments(self):
        network = feed(PostResponses(SHORTCODE, 10), 'post_graphql', 'post_graphql')
        self.assertEqual(len(network.comments), 3)


class RestTests(unittest.TestCase):
    def test_info_and_comments_with_reply_previews(self):
        network = feed(PostResponses(SHORTCODE, 10), 'post_rest')
        self.assertEqual(network.fields, {
            'media_id': MEDIA_ID,
            'owner': 'example_brand',
            'caption': 'کپشن از REST #اسنوا',
            'published_at': '2026-11-01T09:30:00+00:00',
            'total_likes': 980,
            'reported_comment_count': 3,
        })
        # Comment pages wait until read_pending_comments checks the media id.
        self.assertEqual(network.comments, {})
        self.assertEqual(len(network.comment_payloads), 2)
        network.read_pending_comments()
        self.assertEqual(
            [(c['username'], c['text'], c['likes']) for c in network.comments.values()],
            [('rest_user', 'خیلی خوبه', 7), ('reply_user', 'موافقم', 0), ('asker', 'ارسال دارید؟', 1)],
        )
        self.assertEqual(network.comment_responses, 1)
        # The page for media 555 stays queued in case that id is learned later.
        self.assertEqual([media_id for media_id, _ in network.comment_payloads], ['555'])

    def test_comment_payloads_are_capped_per_response_and_in_count(self):
        exchange = load_exchanges('post_rest')[0]
        network = PostResponses(SHORTCODE, 1)
        for _ in range(40):
            network.receive(FakeResponse(exchange))
        self.assertEqual(len(network.comment_payloads), 30)
        self.assertTrue(all(len(items) == 1 for _, items in network.comment_payloads))
        network.read_pending_comments()
        self.assertEqual(len(network.comments), 1)

    def test_comments_for_unknown_media_are_used_once_media_id_is_learned(self):
        exchanges = load_exchanges('post_rest')
        other = exchanges[1]
        network = PostResponses('', 10)
        network.receive(FakeResponse(other))
        network.read_pending_comments()
        self.assertEqual(network.comments, {})
        network.media_ids.add('555')
        network.read_pending_comments()
        self.assertEqual([c['username'] for c in network.comments.values()], ['elsewhere'])


class GraphQLCommentStreamTests(unittest.TestCase):
    def test_guarded_multiline_payload_and_child_comments(self):
        network = feed(PostResponses(SHORTCODE, 10), 'comments_graphql_stream')
        self.assertEqual(
            [c['text'] for c in network.comments.values()],
            ['first page', 'streamed later', 'reply via parent id'],
        )
        self.assertEqual(network.comments['18000000000000021']['likes'], 2)
        self.assertEqual(network.comment_responses, 3)
        self.assertNotIn('18000000000000098', network.comments)

    def test_child_comments_need_a_known_parent(self):
        exchange = load_exchanges('comments_graphql_stream')[1]
        network = PostResponses(SHORTCODE, 10)
        network.receive(FakeResponse(exchange))
        self.assertEqual(network.comments, {})

    def test_variables_may_arrive_in_query_string(self):
        exchange = dict(load_exchanges('comments_graphql_stream')[2])
        exchange['url'] = 'https://www.instagram.com/graphql/query/?' + exchange.pop('post_data')
        exchange['method'] = 'GET'
        network = PostResponses('', 10)
        network.media_ids.add('555')
        network.receive(FakeResponse(exchange))
        self.assertEqual([c['username'] for c in network.comments.values()], ['elsewhere'])


class AccessTests(unittest.TestCase):
    def test_each_block_signal_stops_collection(self):
        for exchange in load_exchanges('blocked'):
            with self.subTest(exchange['name']):
                network = PostResponses(SHORTCODE, 10)
                network.receive(FakeResponse(exchange))
                self.assertTrue(network.blocked)
                with self.assertRaises(CollectionError):
                    network.check_access()

    def test_non_api_responses_are_ignored(self):
        for exchange in load_exchanges('ignored'):
            with self.subTest(exchange['name']):
                network = PostResponses(SHORTCODE, 10)
                network.receive(FakeResponse(exchange))
                self.assertFalse(network.blocked)
                self.assertEqual(network.fields, {})
                self.assertEqual(network.json_responses, 0)

    def test_unreadable_body_is_ignored(self):
        response = FakeResponse(load_exchanges('post_graphql')[0])

        def closed():
            raise Error('Response body is unavailable for redirect responses')

        response.text = closed
        network = PostResponses(SHORTCODE, 10)
        network.receive(response)
        self.assertEqual(network.json_responses, 0)


if __name__ == '__main__':
    unittest.main()
