"""Offline collector tests. No Instagram account or network access is used."""
import sys
import types
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from instaloader import exceptions
from direct_scraper import collect_direct,CollectionError

class Loader:
    fail=False
    two_factor=False
    latest=None
    def __init__(self,**kwargs):
        self.context=types.SimpleNamespace();self.closed=False;Loader.latest=self
    def login(self,*args):
        if self.fail:raise RuntimeError('TEST_SECRET_MARKER')
        if self.two_factor:raise exceptions.TwoFactorAuthRequiredException()
    def two_factor_login(self,code):self.code=code
    def close(self):self.closed=True

class Post:
    shortcode='same-post'
    caption='a caption'
    owner_username='example'
    date_utc=datetime.now(timezone.utc)
    likes=12
    calls=0
    def get_comments(self):
        Post.calls+=1
        for i in range(5):
            yield types.SimpleNamespace(owner=types.SimpleNamespace(username='example'),text=str(i),created_at=self.date_utc,likes_count=0)
    def get_likes(self):raise AssertionError('Unrequested likes must not be fetched')

class DirectCollectorTests(unittest.TestCase):
    def setUp(self):
        Loader.fail=False;Loader.two_factor=False;Post.calls=0
        self.config={'profiles':['example'],'hashtags':['پوست'],'max_posts':2,'max_comments':2,'max_likers':2,'likers':False}
        self.auth={'username':'test','password':'TEST_SECRET_MARKER','code':''}
        self.rows=[]
        profile=types.SimpleNamespace(get_posts=lambda:iter([Post()]))
        hashtag=types.SimpleNamespace(get_posts_resumable=lambda:iter([Post()]))
        module=types.ModuleType('instaloader');module.Instaloader=Loader
        module.Profile=types.SimpleNamespace(from_username=lambda *args:profile)
        module.Hashtag=types.SimpleNamespace(from_name=lambda *args:hashtag)
        module.exceptions=exceptions
        self.patcher=patch.dict(sys.modules,{'instaloader':module})
        self.patcher.start();self.addCleanup(self.patcher.stop)
    def collect(self):collect_direct(self.config,self.auth,self.rows.append,lambda message:None)
    def test_multiple_sources_deduplicate_and_cap_comments(self):
        self.collect()
        self.assertEqual(len(self.rows),1)
        self.assertEqual(Post.calls,1)
        self.assertEqual(len(self.rows[0]['comments']),2)
        self.assertEqual(self.rows[0]['caption'],'a caption')
        self.assertEqual(self.rows[0]['source_type'],'profile')
        self.assertEqual(self.auth,{})
        self.assertTrue(Loader.latest.closed)
    def test_hashtag_only(self):
        self.config['profiles']=[];self.collect()
        self.assertEqual(self.rows[0]['source_type'],'hashtag')
    def test_login_error_is_sanitized_and_credentials_cleared(self):
        Loader.fail=True
        with self.assertRaises(CollectionError) as caught:self.collect()
        self.assertNotIn('TEST_SECRET_MARKER',str(caught.exception))
        self.assertEqual(self.auth,{})
        self.assertTrue(Loader.latest.closed)
    def test_two_factor_code_used(self):
        Loader.two_factor=True;self.auth['code']='123456';self.collect()
        self.assertEqual(Loader.latest.code,'123456')
        self.assertEqual(self.auth,{})
    def test_two_factor_code_requested_after_login_on_same_session(self):
        Loader.two_factor = True
        sessions = []

        def request_code():
            self.assertEqual(self.auth, {})
            sessions.append(Loader.latest)
            return '123456'

        collect_direct(
            self.config, self.auth, self.rows.append, lambda message: None,
            request_code=request_code,
        )
        self.assertEqual(sessions, [Loader.latest])
        self.assertEqual(Loader.latest.code, '123456')
        self.assertEqual(len(self.rows), 1)
    def test_checkpoint_message_omits_private_url(self):
        failure = exceptions.LoginException('Login: Checkpoint required. /challenge/PRIVATE_TOKEN')
        with patch.object(Loader, 'login', side_effect=failure):
            with self.assertRaises(CollectionError) as caught:
                self.collect()
        message = str(caught.exception)
        self.assertIn('مرحلهٔ ورود به حساب', message)
        self.assertIn('تأیید امنیتی', message)
        self.assertNotIn('PRIVATE_TOKEN', message)
    def test_checkpoint_uses_manual_sign_in_and_continues_collection(self):
        failure = exceptions.LoginException('Login: Checkpoint required. /challenge/PRIVATE_TOKEN')
        recovered = []

        def recover(username, loader):
            self.assertEqual(self.auth, {})
            self.assertEqual(username, 'test')
            self.assertIs(loader, Loader.latest)
            recovered.append(username)

        with patch.object(Loader, 'login', side_effect=failure):
            collect_direct(
                self.config, self.auth, self.rows.append, lambda message: None,
                request_code=lambda: self.fail('A checkpoint is not a code request'),
                recover_login=recover,
            )
        self.assertEqual(recovered, ['test'])
        self.assertEqual(len(self.rows), 1)
    def test_rejected_second_factor_is_distinguished_from_bad_password(self):
        Loader.two_factor = True
        self.auth['code'] = '123456'
        with patch.object(Loader, 'two_factor_login', side_effect=exceptions.BadCredentialsException()):
            with self.assertRaises(CollectionError) as caught:
                self.collect()
        self.assertIn('کد دومرحله‌ای را نپذیرفت', str(caught.exception))
    def test_missing_two_factor_code_fails_cleanly(self):
        Loader.two_factor=True
        with self.assertRaises(CollectionError):self.collect()
        self.assertEqual(self.auth,{})
        self.assertTrue(Loader.latest.closed)

if __name__=='__main__':unittest.main()
