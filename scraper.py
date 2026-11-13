# Original defaults: max_posts=8; profile_scrolls=3; browser=msedge; viewport=1366x768. Credentials removed.
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import time, random, re
def human_delay(a=0.4, b=1.8):
    time.sleep(random.uniform(a, b))

def type_like_human(locator, text, min_d=0.05, max_d=0.18):
    locator.click()
    human_delay(0.3, 0.8)
    for ch in text:
        locator.type(ch)
        time.sleep(random.uniform(min_d, max_d))
        if random.random() < 0.06:
            time.sleep(random.uniform(0.2, 0.4))

def dismiss_cookies(page):
    for sel in ["button:has-text('Allow all')", "button:has-text('Allow')",
                "button:has-text('Accept')", "button:has-text('Accept All')"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                human_delay(1, 2)
                return
        except:
            pass


# ==================== تشخیص لاگین ====================
def is_signup_wall_visible(page):
    for sel in ["span:has-text('Never miss a post from')",
                "span:has-text('Sign up for Instagram to stay in the loop')",
                "a[href*='desktop_dynamic_landing_dialog']",
                "div[role='dialog'] a[href='/accounts/emailsignup/']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=500):
                return True
        except:
            pass
    return False

def is_login_form_visible(page):
    try:
        return page.locator("form#login_form input[name='pass']").first.is_visible(timeout=500)
    except:
        return False

def has_logged_in_nav(page):
    for sel in ["svg[aria-label='Home']", "svg[aria-label='New post']",
                "a[href='/direct/inbox/']", "svg[aria-label='Search']",
                "svg[aria-label='Explore']", "svg[aria-label='Reels']"]:
        try:
            if page.locator(sel).first.is_visible(timeout=700):
                return True
        except:
            pass
    return False

def is_logged_in(page):
    url = page.url.lower()
    if any(x in url for x in ['/accounts/login', '/accounts/emailsignup',
                              '/challenge', '/two_factor', '/accounts/password']):
        return False
    if is_signup_wall_visible(page):
        return False
    if is_login_form_visible(page):
        return False
    return has_logged_in_nav(page)

def get_login_error(page):
    for sel in ["#slfErrorAlert", "div[role='alert']"]:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=400):
                t = (el.inner_text() or "").strip()
                if t:
                    return t
        except:
            pass
    return None


# ==================== انتظار برای کد تایید ====================
def extract_total_likes(page):
    return page.evaluate(r"""
        () => {
            const normalize = value => (value || '').trim()
                .replace(/[۰-۹٠-٩]/g, digit => String(digit.charCodeAt(0) & 15))
                .replace(/٬/g, ',').replace(/٫/g, '.');
            const number = /^(?:\d+|\d{1,3}(?:,\d{3})+)$/;
            const compact = /^\d+(?:\.\d+)?[KMB]$/i;
            const parse = value => {
                const text = normalize(value);
                if (number.test(text)) return Number(text.replace(/,/g, ''));
                return compact.test(text) ? text.toUpperCase() : null;
            };
            const post = location.pathname.match(/^\/(?:p|reels?)\/([\w-]+)\/?$/);
            if (!post) return null;
            const likesPath = new RegExp('^/(?:p|reels?)/' + post[1] + '/liked_by/?$');
            for (const link of document.querySelectorAll('a[href*="/liked_by/"]')) {
                if (link.origin !== location.origin || !likesPath.test(link.pathname)) continue;
                if (!link.getClientRects().length) continue;
                const count = normalize(link.innerText).replace(/\s+(?:likes?|لایک|پسند)$/i, '');
                const parsed = parse(count);
                if (parsed !== null) return parsed;
            }
            // Instagram's post description can expose a count even without a likes link.
            const metadata = document.querySelector('meta[property="og:description"]');
            const description = normalize(metadata?.content);
            const count = description.match(/^([\d,.]+[KMB]?)\s+likes?,\s+[\d,.]+[KMB]?\s+comments?\s*[-–—]/i);
            return count ? parse(count[1]) : null;
        }
    """)


# ==================== استخراج لایک‌کنندگان ====================
def extract_likers(page, post_url):
    likers = []
    print("     🖱️  استخراج لایک‌کنندگان...")

    m = re.search(r'/p/([^/]+)/', post_url)
    if not m:
        print("     ⚠️ shortcode پیدا نشد.")
        return likers
    shortcode = m.group(1)

    liked_by_url = f"https://www.instagram.com/p/{shortcode}/liked_by/"
    print(f"     🌐 ناوبری به: {liked_by_url}")
    try:
        page.goto(liked_by_url, wait_until="domcontentloaded", timeout=40000)
    except Exception as e:
        print(f"     ❌ خطا در ناوبری: {e}")
        return likers
    human_delay(4, 6)

    if is_signup_wall_visible(page) or is_login_form_visible(page):
        print("     ❌ عدم دسترسی (لاگین معتبر نیست).")
        return likers

    # صبر برای مودال یا لیست
    try:
        page.wait_for_selector("div[role='dialog'] a[href^='/'], main ul li, article ul li", timeout=15000)
        print("     ✅ لیست لایک‌کننده‌ها بارگذاری شد.")
    except PWTimeout:
        print("     ⚠️ لیست در زمان مقرر بارگذاری نشد.")
        try:
            None
        except:
            pass
        return likers

    human_delay(2, 4)

    # اسکرول داخل مودال یا صفحه
    print("     ⏳ اسکرول برای بارگذاری همه...")
    last_count = -1
    for _ in range(30):
        page.evaluate("""
            () => {
                const dialog = document.querySelector("div[role='dialog']");
                if (dialog) {
                    for (const el of dialog.querySelectorAll('*')) {
                        const s = getComputedStyle(el);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                            el.scrollHeight > el.clientHeight + 10) {
                            el.scrollTop = el.scrollHeight;
                            return;
                        }
                    }
                    return;
                }
                let best = null, bestScore = 0;
                for (const el of document.querySelectorAll('div, ul')) {
                    const s = getComputedStyle(el);
                    if (s.overflowY !== 'auto' && s.overflowY !== 'scroll') continue;
                    if (el.scrollHeight <= el.clientHeight + 10) continue;
                    const c = el.querySelectorAll('a[href^="/"]').length;
                    if (c > bestScore) { bestScore = c; best = el; }
                }
                if (best) best.scrollTop = best.scrollHeight;
                else window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        human_delay(1.5, 2.5)
        current = page.evaluate("""
            () => {
                const d = document.querySelector("div[role='dialog']");
                const root = d || document;
                return root.querySelectorAll('a[href^="/"]').length;
            }
        """)
        if current == last_count:
            break
        last_count = current

    # استخراج نام‌ها
    likers = page.evaluate("""
        () => {
            const results = [];
            const seen = new Set();
            const d = document.querySelector("div[role='dialog']");
            const root = d || document;
            const links = root.querySelectorAll('a[href^="/"]');
            for (const a of links) {
                const href = a.getAttribute('href') || '';
                const parts = href.split('/').filter(p => p);
                if (parts.length === 1 && parts[0].length >= 2 && parts[0].length <= 50 && parts[0] !== 'explore') {
                    if (!seen.has(parts[0])) {
                        seen.add(parts[0]);
                        results.push(parts[0]);
                    }
                }
            }
            return results;
        }
    """)
    print(f"     ✅ {len(likers)} لایک‌کننده استخراج شد.")
    return likers


# ==================== استخراج کامنت‌ها ====================
def extract_comments(page, post_url):
    comments = []
    print("     💬  استخراج کامنت‌ها از پنل پست...")

    if post_url not in page.url:
        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=40000)
            human_delay(3, 5)
        except Exception as e:
            print(f"     ❌ خطا در بازگشت به پست: {e}")
            return comments

    loaded = False
    for sel in ["ul._a9ym li._a9zj", "article ul li", "main ul li"]:
        try:
            page.wait_for_selector(sel, timeout=12000)
            print(f"     ✅ لیست کامنت‌ها بارگذاری شد (سلکتور: {sel})")
            loaded = True
            break
        except PWTimeout:
            continue

    if not loaded:
        print("     ⚠️ هیچ کامنتی بارگذاری نشد.")
        try:
            None
        except:
            pass
        return comments

    human_delay(2, 4)

    # کلیک روی "View all comments" در صورت وجود
    try:
        page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('span, div[role="button"], button')) {
                    const t = (el.innerText || '').trim();
                    if (/view (all )?[\\d,]+ comments?/i.test(t) && !/limited|hidden/i.test(t)) {
                        (el.closest('div[role="button"], a, button') || el).click();
                        return;
                    }
                }
            }
        """)
        human_delay(2, 3)
    except:
        pass

    # اسکرول در پنل کامنت‌ها
    print("     ⏳ اسکرول در پنل کامنت‌ها...")
    last_count = -1
    for _ in range(30):
        page.evaluate("""
            () => {
                let best = null, bestScore = 0;
                for (const el of document.querySelectorAll('div, ul')) {
                    const s = getComputedStyle(el);
                    if (s.overflowY !== 'auto' && s.overflowY !== 'scroll') continue;
                    if (el.scrollHeight <= el.clientHeight + 10) continue;
                    const c = el.querySelectorAll('li._a9zj').length;
                    if (c > bestScore) { bestScore = c; best = el; }
                }
                if (best) best.scrollTop = best.scrollHeight;
                else window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        human_delay(2, 3)
        current = page.evaluate("document.querySelectorAll('li._a9zj').length")
        if current == last_count:
            break
        last_count = current

    # استخراج دقیق
    comments = page.evaluate("""
        () => {
            const results = [];
            const seen = new Set();
            const lis = document.querySelectorAll('ul._a9ym li._a9zj');

            for (const li of lis) {
                let username = null;
                const userLink = li.querySelector("h3 a[href^='/'][role='link']");
                if (userLink) {
                    const href = userLink.getAttribute('href') || '';
                    const parts = href.split('/').filter(p => p);
                    if (parts.length === 1) username = parts[0];
                }
                if (!username) {
                    for (const a of li.querySelectorAll('a[href^="/"][role="link"]')) {
                        const href = a.getAttribute('href') || '';
                        const parts = href.split('/').filter(p => p);
                        if (parts.length === 1 && parts[0].length >= 2 && parts[0].length <= 50) {
                            username = parts[0];
                            break;
                        }
                    }
                }
                if (!username) continue;

                let text = '';
                const textSpan = li.querySelector("span._ap3a._aaco, span._ap3a");
                if (textSpan) {
                    text = (textSpan.innerText || '').trim();
                }
                if (!text) {
                    for (const sp of li.querySelectorAll('span[dir="auto"]')) {
                        if (sp.closest('a')) continue;
                        const t = (sp.innerText || '').trim();
                        if (t && t !== username && t.length > text.length &&
                            !/^\\d+\\s*(likes?|h|m|d|w|hr|min)$/i.test(t) &&
                            !/^(reply|like|see translation|view all|view hidden)$/i.test(t)) {
                            text = t;
                        }
                    }
                }
                if (!text) continue;

                let comment_time = null;
                const timeEl = li.querySelector("time[datetime]");
                if (timeEl) comment_time = timeEl.getAttribute('datetime');

                let comment_likes = 0;
                for (const btn of li.querySelectorAll("button._a9ze")) {
                    const bt = (btn.innerText || '').trim();
                    const mm = bt.match(/^(\\d+)\\s+likes?$/i);
                    if (mm) { comment_likes = parseInt(mm[1], 10); break; }
                }

                const key = username + '::' + text;
                if (seen.has(key)) continue;
                seen.add(key);
                results.push({
                    username: username,
                    text: text.substring(0, 500),
                    time: comment_time,
                    likes: comment_likes
                });
            }
            return results;
        }
    """)
    print(f"     ✅ {len(comments)} کامنت استخراج شد.")
    return comments


# ==================== main ====================

