"""Try one Instagram hashtag and one comment through instagrapi."""

import argparse
from datetime import datetime, timezone
from getpass import getpass
import logging
import re
import sys

from direct_scraper import CollectionError


def paced(request, throttle):
    def send(*args, **kwargs):
        throttle.before_request()
        return request(*args, **kwargs)
    return send


def collect_hashtags(tags, credentials, request_code, report, save, *, max_posts, max_comments, known_posts=()):
    """Collect a bounded number of results per hashtag, reusing one saved device and session."""
    try:
        from instagrapi import Client
        from instagrapi.exceptions import AccountSuspended, ChallengeRequired, TwoFactorRequired
    except ImportError:
        raise CollectionError('کتابخانهٔ آزمون مستقیم نصب نیست. requirements.txt را نصب کنید.') from None
    from safety import Throttle, account_key, classify_restriction, protect_file, session_path

    username = credentials.get('username', '').strip()
    throttle = Throttle(account_key('instagrapi', username), report)
    try:
        throttle.check()
    except CollectionError:
        credentials.clear()
        raise
    settings = session_path('instagrapi', username)

    logger = logging.Logger('instagram_probe')
    logger.disabled = True
    client = Client(logger=logger, request_timeout=20, session_retry_total=0)
    client.private_request_logger = logger
    client.challenge_code_handler = lambda *_: request_code()

    def stop_on_password_change(_username):
        raise ChallengeRequired('Password change requires manual account verification.')

    client.change_password_handler = stop_on_password_change
    # Every request instagrapi sends waits a random, human-scale pause first
    # and counts toward the account's daily budget.
    client.private_request = paced(client.private_request, throttle)
    client.public_request = paced(client.public_request, throttle)
    stage = 'ورود'
    try:
        report('دریافت مستقیم با instagrapi آغاز شد.')
        if settings.exists():
            try:
                # Same device ids and cookies as last time: Instagram sees one
                # phone that stays signed in, not a new device every run.
                client.load_settings(settings)
                report('دستگاه و نشست ذخیره‌شدهٔ قبلی استفاده می‌شود.')
            except Exception:
                report('تنظیمات ذخیره‌شده خوانده نشد؛ یک بار دوباره وارد می‌شویم.')
        client.username = username
        client.password = credentials.get('password', '')
        if not client.password and not settings.exists():
            raise CollectionError('نشست ذخیره‌شده‌ای برای این حساب نیست. رمز حساب را وارد کنید.')
        try:
            logged_in = client.login()
        except TwoFactorRequired:
            logged_in = client.login(verification_code=request_code())
        finally:
            credentials.clear()
        if not logged_in:
            raise CollectionError('ورود به حساب در دریافت مستقیم موفق نبود.')
        client.password = None
        client.dump_settings(settings)
        protect_file(settings)
        report('ورود موفق بود و نشست برای اجراهای بعدی ذخیره شد.')

        seen_posts = set()
        known = set(known_posts)
        for index, tag in enumerate(tags):
            if index:
                throttle.between_sources()
            report(f'دریافت هشتگ: #{tag}')
            for tab, label in (('recent', 'اخیر'), ('top', 'برتر')):
                stage = f'دریافت پست‌های {label} هشتگ #{tag}'
                posts = read_tag_posts(client, tag, tab, max_posts)
                if posts:
                    break
                report(f'بخش پست‌های {label} نتیجه‌ای نداد.')
            else:
                report(f'برای #{tag} پستی دریافت نشد.')
                continue

            saved = 0
            for post in posts:
                if post.id in seen_posts or post.code in known:
                    continue
                throttle.before_post()
                stage = f'دریافت کامنت‌های هشتگ #{tag}'
                comments = [
                    {
                        'username': item.user.username,
                        'text': item.text,
                        'time': item.created_at_utc.isoformat(),
                        'likes': item.like_count,
                    }
                    for item in client.media_comments(post.id, amount=max_comments)[:max_comments]
                ]
                stage = f'ذخیرهٔ پست هشتگ #{tag}'
                save({
                    'post_url': f'https://www.instagram.com/p/{post.code}/',
                    'caption': post.caption_text or '',
                    'owner': post.user.username,
                    'published_at': post.taken_at.isoformat(),
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                    'total_likes': post.like_count,
                    'source': tag,
                    'source_type': 'hashtag',
                    'comments': comments,
                    'likers': [],
                    'collection_method': 'instagrapi',
                })
                seen_posts.add(post.id)
                saved += 1
            report(f'#{tag}، بخش {label}: {saved} پست جدید از {len(posts)} نتیجه ذخیره شد.')
    except AccountSuspended:
        throttle.restrict('suspended')
        raise CollectionError(
            'اینستاگرام در پاسخ به درخواست، تعلیق حساب را اعلام کرد. '
            'وضعیت حساب را در خود اینستاگرام بررسی کنید و در صورت نمایش گزینهٔ بررسی مجدد، مراحل آن را دنبال کنید.'
        ) from None
    except CollectionError:
        raise
    except Exception as error:
        kind = classify_restriction(error)
        if kind:
            raise throttle.restrict(kind) from None
        # Never log upstream exception text, which may contain session data.
        raise CollectionError(f'مرحلهٔ {stage} ناموفق بود ({type(error).__name__}).') from None
    finally:
        credentials.clear()
        client.private.close()
        client.public.close()


def read_tag_posts(client, tag, tab, limit):
    posts = {}
    cursor = None
    seen_cursors = set()
    while len(posts) < limit:
        batch, next_cursor = client.hashtag_medias_v1_chunk(
            tag, max_amount=limit, tab_key=tab, max_id=cursor,
        )
        new_posts = len(posts)
        for post in batch:
            posts.setdefault(post.id, post)
            if len(posts) == limit:
                break
        if len(posts) == new_posts or not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return list(posts.values())


def probe_hashtag(tag, credentials, request_code, report):
    posts = []
    collect_hashtags(
        [tag], credentials, request_code, report, posts.append,
        max_posts=1, max_comments=1,
    )
    if not posts:
        return None
    post = posts[0]
    if post['comments']:
        report('آزمون موفق بود. یک پست و یک کامنت بدون مرورگر دریافت شدند.')
    else:
        report('یک پست دریافت شد. درخواست کامنت پاسخی با فهرست خالی برگرداند.')
    return post


def main():
    parser = argparse.ArgumentParser(description='Test browser-free Instagram hashtag and comment access.')
    parser.add_argument('hashtag', nargs='?', default='لوازم_خانگی')
    tag = parser.parse_args().hashtag.strip().lstrip('#')
    if not re.fullmatch(r'[\w\u200c]{1,100}', tag):
        parser.error('Enter one hashtag.')
    if not sys.stdin.isatty():
        parser.error('Run this command in an interactive terminal.')

    credentials = {
        'username': input('نام کاربری اینستاگرام: ').strip(),
        'password': getpass('رمز اینستاگرام: '),
    }
    try:
        post = probe_hashtag(tag, credentials, lambda: getpass('کد تأیید اینستاگرام: ').strip(), print)
    except CollectionError as error:
        print(error)
        return 1
    return 0 if post and post['comments'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
