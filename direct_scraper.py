"""Direct requests through Instaloader; no browser or downloaded media.

The Instagram session (cookies, not the password) is saved under the Didban
state folder and reused, so each run does not log in again.
"""
from itertools import islice
from datetime import datetime,timezone

class CollectionError(Exception):
    """Only fixed, credential-free messages may be shown to the user."""

def is_security_challenge(error):
    detail = str(error).lower()
    return any(marker in detail for marker in (
        'checkpoint required', 'checkpoint_required', 'challenge_required',
    ))

def describe_failure(error, stage, errors):
    from requests.exceptions import RequestException

    # Classify upstream errors in memory. Their text can include account
    # identifiers, response bodies, or checkpoint URLs, so never return it.
    if isinstance(error, errors.BadCredentialsException):
        if stage == 'تأیید دومرحله‌ای':
            return 'اینستاگرام کد دومرحله‌ای را نپذیرفت. با یک کد تازه دوباره اجرا کنید.'
        return 'اینستاگرام رمز حساب را نپذیرفت. نام کاربری و رمز را بررسی کنید.'
    if isinstance(error, (errors.LoginException, errors.AbortDownloadException)):
        detail = str(error).lower()
        if is_security_challenge(error):
            return 'اینستاگرام تأیید امنیتی خواست. در برنامه یا سایت رسمی اینستاگرام تأیید را کامل کنید.'
        if 'feedback_required' in detail:
            return 'اینستاگرام درخواست مستقیم را متوقف کرد (feedback_required). وضعیت حساب را در اینستاگرام بررسی کنید.'
        if 'does not exist' in detail and isinstance(error, errors.LoginException):
            return 'اینستاگرام نام کاربری ورود را پیدا نکرد. نام کاربری حساب را بررسی کنید.'
        if 'json decode fail, 429' in detail:
            return 'اینستاگرام تعداد درخواست‌ها را محدود کرده است (۴۲۹). بعداً دوباره امتحان کنید.'
        if isinstance(error, errors.LoginException):
            return 'اینستاگرام پاسخ ورود قابل استفاده‌ای به Instaloader نداد. ابتدا ورود همین حساب را در سایت رسمی بررسی کنید.'
        return 'اینستاگرام ادامهٔ درخواست‌ها را متوقف کرد. وضعیت حساب را در سایت رسمی بررسی کنید.'
    if isinstance(error, errors.TooManyRequestsException):
        return 'اینستاگرام تعداد درخواست‌ها را محدود کرده است (۴۲۹). بعداً دوباره امتحان کنید.'
    if isinstance(error, errors.LoginRequiredException):
        return 'اینستاگرام ورود دوباره به حساب را خواست.'
    if isinstance(error, errors.PrivateProfileNotFollowedException):
        return 'حساب ورود به محتوای این پیج خصوصی دسترسی ندارد.'
    if isinstance(error, (errors.ProfileNotExistsException, errors.QueryReturnedNotFoundException)):
        return 'اینستاگرام منبع یا محتوای درخواستی را پیدا نکرد.'
    if isinstance(error, errors.QueryReturnedForbiddenException):
        return 'اینستاگرام دسترسی به محتوای درخواستی را رد کرد (۴۰۳).'
    if isinstance(error, (errors.ConnectionException, RequestException)):
        detail = str(error).casefold()
        if '401 unauthorized' in detail:
            return 'اینستاگرام درخواست دریافت مستقیم را رد کرد (۴۰۱).'
        if '403 forbidden' in detail:
            return 'اینستاگرام دسترسی به محتوای درخواستی را رد کرد (۴۰۳).'
        if '429 too many requests' in detail:
            return 'اینستاگرام تعداد درخواست‌ها را محدود کرده است (۴۲۹). بعداً دوباره امتحان کنید.'
        return 'درخواست به اینستاگرام با خطای ارتباطی مواجه شد.'
    return 'خطای پیش‌بینی‌نشده رخ داد.'

def polite_rate_controller(instaloader, throttle):
    class PoliteRateController(instaloader.RateController):
        """Instaloader's own limits plus a random human-scale pause per request."""

        def wait_before_query(self, query_type):
            super().wait_before_query(query_type)
            throttle.before_request()

    return lambda context: PoliteRateController(context)


def restore_session(loader, username, log):
    from safety import session_path

    path = session_path('instaloader', username)
    if not path.exists():
        return False
    try:
        loader.load_session_from_file(username, str(path))
        if loader.test_login() == username:
            log('نشست ذخیره‌شدهٔ قبلی استفاده شد؛ ورود دوباره لازم نبود.')
            return True
    except Exception:
        pass
    log('نشست ذخیره‌شده دیگر معتبر نیست؛ یک بار دوباره وارد می‌شویم.')
    return False


def keep_session(loader, username):
    from safety import protect_file, session_path

    path = session_path('instaloader', username)
    try:
        loader.save_session_to_file(str(path))
        protect_file(path)
    except Exception:
        pass


def collect_direct(config, credentials, save, log, request_code=None, recover_login=None, known_posts=()):
    try:
        import instaloader
        from instaloader import exceptions as errors
    except ImportError:
        raise CollectionError('کتابخانه روش مستقیم نصب نیست؛ نصب requirements.txt را دوباره اجرا کنید.') from None
    from safety import Throttle, account_key, classify_restriction

    username = credentials.get('username', '')
    throttle = Throttle(account_key('direct', username), log)
    try:
        throttle.check()
    except CollectionError:
        credentials.clear()
        raise
    loader=instaloader.Instaloader(quiet=True,max_connection_attempts=1,request_timeout=30,
                                   rate_controller=polite_rate_controller(instaloader, throttle))
    loader.context.error=lambda *args,**kwargs: None
    stage = 'ورود به حساب'
    try:
        if not restore_session(loader, username, log):
            if not credentials.get('password'):
                raise CollectionError('نشست ذخیره‌شده‌ای برای این حساب نیست. رمز حساب را وارد کنید.')
            log('ورود مستقیم به اینستاگرام؛ مرورگری باز نمی‌شود.')
            try:
                loader.login(credentials['username'],credentials['password'])
            except errors.TwoFactorAuthRequiredException:
                stage = 'تأیید دومرحله‌ای'
                code = credentials.get('code', '').strip()
                credentials.clear()
                if not code and request_code is not None:
                    code = request_code()
                if not code:
                    raise CollectionError('اینستاگرام کد دومرحله‌ای می‌خواهد.')
                try:
                    loader.two_factor_login(code)
                finally:
                    del code
            except (errors.LoginException, errors.AbortDownloadException) as error:
                if recover_login is None or not is_security_challenge(error):
                    raise
                credentials.clear()
                stage = 'تأیید امنیتی در مرورگر'
                recover_login(username, loader)
            keep_session(loader, username)
            log('ورود به حساب انجام شد و نشست برای اجراهای بعدی ذخیره شد.')
        credentials.clear()
        sources=[('profile',name) for name in config.get('profiles',[])]+[('hashtag',name) for name in config.get('hashtags',[])]
        if not sources:sources=[('profile',config['target'])]
        seen=set(known_posts)
        count=skipped=0
        for index,(kind,name) in enumerate(sources):
            if index:throttle.between_sources()
            source_stage = 'دریافت پست‌های پیج' if kind == 'profile' else 'دریافت پست‌های هشتگ'
            stage = source_stage
            log(('دریافت پیج: ' if kind=='profile' else 'دریافت هشتگ: #')+name)
            if kind=='profile':
                posts=instaloader.Profile.from_username(loader.context,name).get_posts()
            else:
                posts=instaloader.Hashtag.from_name(loader.context,name).get_posts_resumable()
            for post in islice(posts,config['max_posts']):
                if post.shortcode in seen:
                    skipped+=post.shortcode in known_posts
                    continue
                seen.add(post.shortcode)
                throttle.before_post()
                stage = 'دریافت کامنت‌ها'
                comments=[]
                for comment in islice(post.get_comments(),config['max_comments']):
                    comments.append({'username':comment.owner.username,'text':comment.text,
                                     'time':comment.created_at.isoformat(),'likes':getattr(comment,'likes_count',None)})
                likers=[]
                if config['likers']:
                    stage = 'دریافت لایک‌کننده‌ها'
                    likers=[user.username for user in islice(post.get_likes(),config['max_likers'])]
                stage = 'ذخیرهٔ پست'
                save({'post_url':'https://www.instagram.com/p/'+post.shortcode+'/',
                      'caption':post.caption or '', 'owner':post.owner_username,
                      'published_at':post.date_utc.isoformat(),'source':name,'source_type':kind,
                      'scraped_at':datetime.now(timezone.utc).isoformat(),'total_likes':post.likes,
                      'comments':comments,'comments_count':len(comments),'likers':likers,'likers_count':len(likers),
                      'collection_method':'direct','comment_limit':config['max_comments']})
                count+=1
                log(f'پست {count} ذخیره شد؛ {len(comments)} کامنت و {len(likers)} لایک‌کننده دریافت شد.')
                stage = source_stage
        if skipped:log(f'{skipped} پست قبلاً ثبت شده بود و دوباره دریافت نشد.')
        if not count and not skipped:raise CollectionError('پست قابل دسترسی پیدا نشد.')
    except CollectionError:
        raise
    except Exception as error:
        kind = classify_restriction(error)
        if kind:
            raise throttle.restrict(kind, f'مرحلهٔ {stage} ناموفق بود. ') from None
        detail = describe_failure(error, stage, errors)
        raise CollectionError(f'مرحلهٔ {stage} ناموفق بود. {detail}') from None
    finally:
        credentials.clear()
        loader.close()
