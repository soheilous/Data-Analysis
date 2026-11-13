"""Manual Instagram sign-in in a temporary browser context."""

import re
from time import monotonic
from urllib.parse import urlsplit

from playwright.sync_api import Error, TimeoutError as PlaywrightTimeout, sync_playwright

from direct_scraper import CollectionError
from scraper import is_logged_in


INSTAGRAM_ORIGIN = 'https://www.instagram.com'


def wait_for_instagram_login(page):
    deadline = monotonic() + 300
    while monotonic() < deadline:
        if page.is_closed():
            raise CollectionError('پنجرهٔ ورود قبل از تکمیل تأیید بسته شد.')
        if urlsplit(page.url).hostname == 'www.instagram.com' and is_logged_in(page):
            return
        page.wait_for_timeout(1000)
    raise CollectionError('مهلت ورود در مرورگر تمام شد.')


def verify_profile_owner(page, username):
    profile_path = f'/{username}/'
    page.goto(INSTAGRAM_ORIGIN + profile_path, wait_until='domcontentloaded', timeout=30_000)
    edit_profile = page.locator(
        'main a[href^="/accounts/edit"], main a[href^="https://www.instagram.com/accounts/edit"]'
    ).or_(page.get_by_role('button', name='Edit profile', exact=True))
    try:
        edit_profile.first.wait_for(state='visible', timeout=12_000)
    except PlaywrightTimeout:
        raise CollectionError(
            'مالکیت حساب در مرورگر تأیید نشد. با همان حسابی که در پروژه وارد کرده‌اید وارد شوید.'
        ) from None
    location = urlsplit(page.url)
    if location.hostname != 'www.instagram.com' or location.path.casefold() != profile_path.casefold():
        raise CollectionError('صفحهٔ حساب موردنظر در مرورگر باز نشد.')


def get_instagram_session(username):
    if not re.fullmatch(r'[A-Za-z0-9_.]{1,30}', username) or username in ('.', '..'):
        raise CollectionError('نام کاربری ورود را بدون @ و بدون لینک وارد کنید.')
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            try:
                context = browser.new_context(locale='en-US')
                page = context.new_page()
                page.goto(INSTAGRAM_ORIGIN + '/accounts/login/', wait_until='domcontentloaded', timeout=30_000)
                wait_for_instagram_login(page)
                verify_profile_owner(page, username)
                cookies = {
                    cookie['name']: cookie['value']
                    for cookie in context.cookies(INSTAGRAM_ORIGIN)
                }
                if cookies.get('sessionid') and cookies.get('csrftoken'):
                    return cookies
                raise CollectionError('اطلاعات نشست پس از ورود در مرورگر در دسترس نبود.')
            finally:
                browser.close()
    except Error:
        raise CollectionError(
            'باز کردن یا استفاده از مرورگر ورود ممکن نشد. نصب Chromium برای Playwright را بررسی کنید.'
        ) from None
