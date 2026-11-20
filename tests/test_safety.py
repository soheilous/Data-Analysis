"""Pacing, daily budgets and cooldowns. No Instagram account or network access is used."""
import importlib
import os
import random
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from instaloader import exceptions

import safety
from direct_scraper import CollectionError, collect_direct


class StateDirTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.dict(os.environ, {'DIDBAN_STATE_DIR': folder.name, 'DIDBAN_PAUSE_SCALE': '0'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = folder.name


class ThrottleTests(StateDirTestCase):
    def throttle(self, key='direct-a', **limits):
        self.pauses = []
        return safety.Throttle(
            key, limits=safety.Limits(**limits), sleep=self.pauses.append, rng=random.Random(1),
        )

    def test_daily_request_budget_stops_the_run(self):
        throttle = self.throttle(daily_requests=2)
        throttle.before_request()
        throttle.before_request()
        with self.assertRaises(CollectionError) as caught:
            throttle.before_request()
        self.assertIn('سقف روزانه', str(caught.exception))
        # The budget is per account and survives a new run.
        with self.assertRaises(CollectionError):
            self.throttle(daily_requests=2).check()
        self.throttle('direct-b', daily_requests=2).check()

    def test_daily_post_budget(self):
        throttle = self.throttle(daily_posts=1)
        throttle.before_post()
        with self.assertRaises(CollectionError):
            throttle.before_post()

    def test_every_request_waits_a_random_pause(self):
        throttle = self.throttle()
        for _ in range(3):
            throttle.before_request()
        self.assertEqual(len(self.pauses), 3)
        self.assertTrue(all(3 <= pause <= 8 for pause in self.pauses))
        self.assertEqual(len(set(self.pauses)), 3)

    def test_posts_are_spaced_with_a_long_break(self):
        throttle = self.throttle(break_every_posts=3)
        for _ in range(4):
            throttle.before_post()
        # No pause before the first post, normal pauses, then a long break.
        self.assertEqual(len(self.pauses), 3)
        self.assertTrue(all(10 <= pause <= 25 for pause in self.pauses[:2]))
        self.assertGreaterEqual(self.pauses[2], 90)

    def test_restriction_sets_a_cooldown_for_that_account_only(self):
        error = self.throttle().restrict('feedback')
        self.assertIsInstance(error, safety.AccountRestricted)
        self.assertIn('feedback_required', str(error))
        with self.assertRaises(CollectionError) as caught:
            self.throttle().check()
        self.assertIn('متوقف است', str(caught.exception))
        self.throttle('direct-b').check()

    def test_account_key_hides_username(self):
        key = safety.account_key('direct', 'Example.User')
        self.assertNotIn('example', key.casefold())
        self.assertEqual(key, safety.account_key('direct', ' example.user '))

    def test_classify_restriction(self):
        cases = {
            exceptions.TooManyRequestsException('429 Too Many Requests'): 'rate_limit',
            exceptions.ConnectionException('JSON Query: HTTP error code 429 Too Many Requests'): 'rate_limit',
            exceptions.AbortDownloadException('feedback_required'): 'feedback',
            exceptions.LoginException('Checkpoint required. /challenge/x'): 'challenge',
            type('ChallengeRequired', (Exception,), {})('x'): 'challenge',
            type('PleaseWaitFewMinutes', (Exception,), {})('x'): 'rate_limit',
            exceptions.BadCredentialsException('wrong password'): None,
            exceptions.ConnectionException('post 4290 not found'): None,
        }
        for error, kind in cases.items():
            with self.subTest(error=error):
                self.assertEqual(safety.classify_restriction(error), kind)


class Post:
    date_utc = datetime.now(timezone.utc)
    caption = ''
    owner_username = 'example'
    likes = 1

    def __init__(self, shortcode):
        self.shortcode = shortcode

    def get_comments(self):
        return iter(())


class Loader:
    instances = []
    session_user = None
    fail_with = None

    def __init__(self, **kwargs):
        self.context = types.SimpleNamespace()
        self.logins = 0
        self.rate_controller = kwargs.get('rate_controller')
        Loader.instances.append(self)

    def login(self, *args):
        self.logins += 1

    def load_session_from_file(self, username, path):
        self.loaded = path

    def test_login(self):
        return Loader.session_user

    def save_session_to_file(self, path):
        with open(path, 'w') as handle:
            handle.write('{}')

    def close(self):
        pass


class DirectSafetyTests(StateDirTestCase):
    def setUp(self):
        super().setUp()
        Loader.instances = []
        Loader.session_user = None
        Loader.fail_with = None

        def posts():
            if Loader.fail_with:
                raise Loader.fail_with
            return iter([Post('old'), Post('new')])

        module = types.ModuleType('instaloader')
        module.Instaloader = Loader
        module.RateController = type('RateController', (), {'__init__': lambda self, context: None,
                                                            'wait_before_query': lambda self, kind: None})
        module.Profile = types.SimpleNamespace(
            from_username=lambda *args: types.SimpleNamespace(get_posts=posts))
        module.exceptions = exceptions
        patcher = patch.dict(sys.modules, {'instaloader': module})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = {'profiles': ['example'], 'hashtags': [], 'max_posts': 5, 'max_comments': 2,
                       'max_likers': 0, 'likers': False}

    def collect(self, password='secret', known_posts=()):
        rows, logs = [], []
        collect_direct(self.config, {'username': 'tester', 'password': password, 'code': ''},
                       rows.append, logs.append, known_posts=known_posts)
        return rows, logs

    def test_session_is_saved_then_reused_without_password(self):
        self.collect()
        self.assertEqual(Loader.instances[-1].logins, 1)
        self.assertTrue(safety.session_path('instaloader', 'tester').exists())
        Loader.session_user = 'tester'
        rows, _ = self.collect(password='')
        self.assertEqual(Loader.instances[-1].logins, 0)
        self.assertEqual(len(rows), 2)

    def test_missing_session_and_password_fails_cleanly(self):
        with self.assertRaises(CollectionError) as caught:
            self.collect(password='')
        self.assertIn('رمز', str(caught.exception))

    def test_known_posts_are_not_fetched_again(self):
        rows, logs = self.collect(known_posts={'old'})
        self.assertEqual([row['post_url'] for row in rows], ['https://www.instagram.com/p/new/'])
        self.assertTrue(any('قبلاً ثبت' in line for line in logs))

    def test_rate_limit_stops_and_blocks_next_run_before_login(self):
        Loader.fail_with = exceptions.TooManyRequestsException('429 Too Many Requests')
        with self.assertRaises(safety.AccountRestricted):
            self.collect()
        Loader.fail_with = None
        count = len(Loader.instances)
        with self.assertRaises(CollectionError) as caught:
            self.collect()
        self.assertIn('متوقف است', str(caught.exception))
        self.assertEqual(len(Loader.instances), count)

    def test_rate_controller_paces_every_query(self):
        calls = []
        with patch.object(safety.Throttle, 'before_request', lambda self: calls.append(1)):
            self.collect()
            Loader.instances[-1].rate_controller(None).wait_before_query('other')
        self.assertEqual(calls, [1])


class ConfigLimitTests(unittest.TestCase):
    def test_old_high_limits_are_lowered_not_rejected(self):
        with tempfile.TemporaryDirectory() as data, patch.dict(os.environ, {'DIDBAN_DATA_DIR': data}):
            sys.modules.pop('app', None)
            app = importlib.import_module('app')
            try:
                config = app.Config(method='browser', profiles=['example'], max_posts=100,
                                    max_comments=5000, max_likers=5000, scrolls=30)
            finally:
                sys.modules.pop('app', None)
        self.assertEqual((config.max_posts, config.max_comments, config.max_likers, config.scrolls),
                         (50, 500, 200, 10))


if __name__ == '__main__':
    unittest.main()
