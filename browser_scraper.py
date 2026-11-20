"""Collect posts visible in an Instagram browser session."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
from datetime import datetime, timezone
from unicodedata import normalize
from urllib.parse import parse_qs, quote, unquote, urlsplit

from playwright.sync_api import Error, TimeoutError, sync_playwright

from browser_login import INSTAGRAM_ORIGIN, wait_for_instagram_login
from direct_scraper import CollectionError
from instagram_network import PostResponses
from scraper import extract_likers, extract_total_likes, is_logged_in


POST_LINKS = 'main a[href*="/p/"], main a[href*="/reel/"], main a[href*="/reels/"]'
CAPTION_TAG = re.compile(r'(?<![\w\u200c])[#＃]([\w\u200c]+)')


def parse_post_url(value):
    location = urlsplit(value.strip())
    match = re.fullmatch(r'/(p|reel|reels)/([A-Za-z0-9_-]{1,32})/?', location.path)
    if (
        location.scheme != 'https'
        or location.netloc.lower() not in ('instagram.com', 'www.instagram.com')
        or not match
    ):
        raise ValueError('لینک کامل یک پست یا ریل اینستاگرام را وارد کنید.')
    category, shortcode = match.groups()
    category = 'p' if category == 'p' else 'reel'
    return shortcode, f'{INSTAGRAM_ORIGIN}/{category}/{shortcode}/'


def matches_source(url, kind, name):
    location = urlsplit(url)
    if location.hostname != 'www.instagram.com':
        return False
    path = unquote(location.path).rstrip('/').casefold()
    if kind == 'profile':
        return path == '/' + name.casefold()
    if path == '/explore/tags/' + name.casefold():
        return True
    query = parse_qs(location.query).get('q', [''])[0]
    return path == '/explore/search/keyword' and query.casefold() == '#' + name.casefold()


def find_post_links(page, kind, name, limit, scrolls, check_access=lambda: None, *, discover=False):
    if kind == 'profile':
        paths = [f'/{quote(name, safe="")}/']
    else:
        paths = [
            f'/explore/tags/{quote(name, safe="")}/',
            f'/explore/search/keyword/?q={quote("#" + name, safe="")}',
        ]
        if discover:
            paths.reverse()

    for path in paths:
        response = page.goto(INSTAGRAM_ORIGIN + path, wait_until='domcontentloaded', timeout=40_000)
        if response and response.status in (401, 403, 429):
            raise CollectionError(f'اینستاگرام صفحهٔ منبع را با خطای {response.status} رد کرد.')
        check_access()
        if not matches_source(page.url, kind, name):
            continue
        links = {}
        try:
            page.locator(POST_LINKS).first.wait_for(state='visible', timeout=8_000)
        except TimeoutError:
            continue
        for attempt in range(scrolls + 1):
            check_access()
            if not matches_source(page.url, kind, name):
                break
            for href in page.locator(POST_LINKS).evaluate_all('links => links.map(link => link.href)'):
                location = urlsplit(href)
                if location.hostname != 'www.instagram.com':
                    continue
                match = re.fullmatch(r'/(?:[A-Za-z0-9_.]{1,30}/)?(p|reel|reels)/([\w-]+)/?', location.path, re.ASCII)
                if not match:
                    continue
                category, shortcode = match.groups()
                category = 'p' if category == 'p' else 'reel'
                links.setdefault(shortcode, f'{INSTAGRAM_ORIGIN}/{category}/{shortcode}/')
                if len(links) >= limit:
                    return links
            if attempt < scrolls:
                page.mouse.wheel(0, 850)
                page.wait_for_timeout(1250)
        if links:
            return links
    return {}


def check_page_access(page, responses):
    responses.check_access()
    path = urlsplit(page.url).path
    if path.startswith(('/challenge', '/checkpoint', '/accounts/login', '/accounts/suspended')):
        raise CollectionError('اینستاگرام ورود یا تأیید حساب خواست. اجرا متوقف شد.')


COMMENT_CONTROL = re.compile(
    r'^(?:view|load|show)\s+(?:(?:all|more|[\d,.]+)\s+)*comments$|^comments?$|'
    r'^(?:مشاهده|نمایش)\s+(?:همهٔ?\s+)?(?:[\d٬,]+\s+)?(?:نظرها|نظرات|کامنت‌ها)(?:\s+بیشتر)?$',
    re.I,
)
COMMENT_REPLIES = re.compile(
    r'^(?:view|load|show)\s+(?:all\s+)?(?:[\d,.]+\s+)?(?:more\s+)?repl(?:y|ies)$', re.I,
)
MORE_COMMENTS = re.compile(r'^(?:view|load|show)\s+(?:[\d,.]+\s+)?more\s+comments$', re.I)


def visible_comments(page, limit, *, diagnostics=False):
    return page.evaluate(r"""({limit, diagnostics}) => {
        const panels = 'article, [role="dialog"], main';
        const isVisible = node => node.getClientRects().length > 0;
        const replyLabel = /^(reply|پاسخ|پاسخ دادن)$/i;
        const controlLabel = /^(?:[\d,.]+\s+likes?|like|reply|see translation|view all .* replies|\d+\s*[smhdw])$/i;
        const profile = link => {
            const path = link.pathname.match(/^\/([A-Za-z0-9_.]{1,30})\/?$/);
            if (!path || link.hostname !== location.hostname) return null;
            return link.textContent.trim().replace(/^@/, '').toLowerCase() === path[1].toLowerCase()
                ? path[1] : null;
        };
        const authors = row => [...row.querySelectorAll('a[href]')]
            .filter(link => isVisible(link) && profile(link));
        const rows = new Set(document.querySelectorAll(
            'article [data-testid="comment"], [role="dialog"] [data-testid="comment"], ' +
            'ul._a9ym li._a9zj'
        ));
        // The comment panel can use plain divs. Its Reply action identifies
        // a comment row even when there are no list items or time elements.
        const replies = [...document.querySelectorAll(
            'button, [role="button"], span, div'
        )].filter(node => node.closest(panels) && isVisible(node)
            && replyLabel.test(node.textContent.trim())
            && ![...node.children].some(child => replyLabel.test(child.textContent.trim())));
        const replyNodes = new Set(replies);
        const permalinks = [...document.querySelectorAll('a[href]')].filter(link =>
            isVisible(link) && link.closest(panels) && link.hostname === location.hostname &&
            /^\/(?:p|reel)\/[\w-]+\/c\/\d+\/?$/.test(link.pathname)
        );
        const anchors = new Set([...replies, ...permalinks]);
        for (const anchor of anchors) {
            for (let row = anchor.parentElement; row && !row.matches(panels); row = row.parentElement) {
                const links = authors(row);
                if (!links.length) continue;
                // Mentions are profile links too. Use the first author link and
                // reject containers spanning multiple Reply actions.
                if ((links[0].compareDocumentPosition(anchor) & Node.DOCUMENT_POSITION_FOLLOWING) &&
                    [...replyNodes].filter(other => row.contains(other)).length <= 1) {
                    rows.add(row);
                }
                break;
            }
        }
        const result = [];
        const seenAnchors = new Set();
        const unreadable = new Set();
        const ordered = [...rows].sort((a, b) =>
            a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
        );
        for (const row of ordered) {
            if (result.length >= limit) break;
            if (!isVisible(row)) continue;
            const [author] = authors(row);
            const reply = replies.find(node => row.contains(node));
            const permalink = permalinks.find(node => row.contains(node));
            if (!author || (!reply && !row.matches('[data-testid="comment"], li._a9zj') &&
                !permalink)) {
                unreadable.add(permalink || reply || row);
                continue;
            }
            const identity = permalink || reply || row;
            if (seenAnchors.has(identity)) continue;
            const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT);
            const parts = [];
            for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                const parent = node.parentElement;
                if (!parent || !isVisible(parent) || author.contains(node) ||
                    !(author.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING) ||
                    (reply && (reply.contains(node) ||
                        !(node.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING))) ||
                    (permalink && permalink.contains(node)) ||
                    parent.closest('time, button, [role="button"], svg, [aria-hidden="true"]')) continue;
                const text = node.textContent.trim();
                if (text && !controlLabel.test(text)) parts.push(text);
            }
            const text = parts.join(' ');
            const username = profile(author);
            if (!text) {
                unreadable.add(identity);
                continue;
            }
            seenAnchors.add(identity);
            unreadable.delete(identity);
            result.push({
                comment_id: permalink?.pathname.match(/\/c\/(\d+)\/?$/)?.[1] || null,
                username, text, time: row.querySelector('time[datetime]')?.dateTime || null, likes: null
            });
        }
        return diagnostics ? {
            reply_actions: replies.length, permalinks: permalinks.length,
            candidate_rows: rows.size, unreadable_rows: unreadable.size, readable_rows: result.length
        } : result;
    }""", {'limit': limit, 'diagnostics': diagnostics})


def same_time(first, second):
    """Compare comment times; network uses +00:00 and page time elements use Z with milliseconds."""
    if not first or not second:
        return True
    try:
        return datetime.fromisoformat(first) == datetime.fromisoformat(second)
    except (TypeError, ValueError):
        return first == second


def collect_loaded_comments(page, network, limit):
    visible = {}
    opened_replies = []
    idle_steps = 0
    expanded_count = scroll_count = 0

    def capture_visible():
        occurrences = {}
        for comment in visible_comments(page, limit):
            key = (comment.get('comment_id'), comment['username'].casefold(), comment['text'].strip(), comment['time'])
            occurrences[key] = occurrences.get(key, 0) + 1
            visible.setdefault((*key, occurrences[key]), comment)

    scroll_state = 'no_panel'
    stop_reason = 'سقف مراحل'
    for _ in range(25):
        check_page_access(page, network)
        network.read_pending_comments()
        before = len(visible) + len(network.comments)
        capture_visible()
        if max(len(visible), len(network.comments)) >= limit:
            stop_reason = 'سقف کامنت'
            break
        panel = page.locator('article, [role="dialog"], main')
        controls = panel.get_by_text(COMMENT_REPLIES).or_(
            panel.get_by_role('button', name=MORE_COMMENTS)
        ).or_(panel.locator('svg[aria-label="Load more comments"]'))
        expanded = False
        for control in controls.all():
            # Clicking a clipped control makes Playwright scroll back to it.
            # Expand controls only when they are inside the current panel view.
            in_view = control.evaluate("""node => {
                const box = node.getBoundingClientRect();
                if (!box.width || !box.height || box.top < 0 || box.bottom > innerHeight) return false;
                for (let parent = node.parentElement; parent; parent = parent.parentElement) {
                    if (!/auto|scroll/.test(getComputedStyle(parent).overflowY)) continue;
                    const area = parent.getBoundingClientRect();
                    if (box.top < area.top || box.bottom > area.bottom) return false;
                }
                return true;
            }""")
            if not in_view:
                continue
            handle = control.element_handle(timeout=1500)
            if handle is None or any(handle.evaluate('(node, previous) => node === previous', previous)
                                     for previous in opened_replies):
                continue
            try:
                control.click(timeout=2000)
            except TimeoutError:
                continue
            opened_replies.append(handle)
            expanded = True
            expanded_count += 1
            page.wait_for_timeout(700)
            check_page_access(page, network)
            network.read_pending_comments()
            capture_visible()
            break
        scroll_state = page.evaluate(r"""() => {
                for (const reply of document.querySelectorAll('button, [role="button"], span')) {
                    if (!/^(reply|پاسخ|پاسخ دادن)$/i.test(reply.textContent.trim()) ||
                        !reply.getClientRects().length ||
                        !reply.closest('article, [role="dialog"], main')) continue;
                    for (let panel = reply.parentElement; panel && panel !== document.body;
                         panel = panel.parentElement) {
                        if (!/auto|scroll/.test(getComputedStyle(panel).overflowY) ||
                            panel.scrollHeight <= panel.clientHeight + 2) continue;
                        const before = panel.scrollTop;
                        panel.scrollTop += Math.max(100, Math.floor(panel.clientHeight * .8));
                        return panel.scrollTop > before ? 'moved' : 'bottom';
                    }
                }
                return 'no_panel';
            }""")
        scrolled = scroll_state == 'moved'
        scroll_count += int(scrolled)
        progress = len(visible) + len(network.comments) > before or expanded or scrolled
        idle_steps = 0 if progress else idle_steps + 1
        if idle_steps >= 3:
            stop_reason = 'انتهای پنل، بدون نتیجهٔ تازه' if scroll_state == 'bottom' else 'پنل قابل اسکرول پیدا نشد'
            break
        page.wait_for_timeout(700)
    check_page_access(page, network)
    network.read_pending_comments()
    capture_visible()
    comments = list(network.comments.values())
    unmatched = comments.copy()
    for comment in visible.values():
        for index, candidate in enumerate(unmatched):
            if (
                (not candidate.get('comment_id') or not comment.get('comment_id')
                 or candidate['comment_id'] == comment['comment_id'])
                and candidate['username'].casefold() == comment['username'].casefold()
                and candidate['text'].strip() == comment['text'].strip()
                and same_time(candidate['time'], comment['time'])
            ):
                unmatched.pop(index)
                break
        else:
            comments.append(comment)
    return comments[:limit], expanded_count, scroll_count, stop_reason, len(visible)


def normalized_tag(value):
    return normalize('NFC', value).casefold()


def visible_post_details(page):
    return page.evaluate(r"""() => {
        const caption = document.querySelector('[data-testid="post-caption"], article h1, main h1');
        const header = document.querySelector('article header, main header, [role="dialog"] header');
        const owner = header && [...header.querySelectorAll('a[href]')].map(a => {
            const match = a.getAttribute('href')?.match(/^\/([A-Za-z0-9_.]{1,30})\/?(?:\?.*)?$/);
            return match?.[1];
        }).find(name => name && !['explore', 'accounts', 'direct', 'reels'].includes(name.toLowerCase()));
        const description = document.querySelector('meta[property="og:description"]')?.content || '';
        const metadataCaption = description.match(/:\s*["“]([\s\S]*)["”]\.?(?:\s|[\u200e\u200f])*$/);
        return {caption: caption?.textContent?.trim() || metadataCaption?.[1]?.trim() || null, owner: owner || null};
    }""")


def matching_caption(page, network_caption, required_tags):
    captions = [network_caption, visible_post_details(page)['caption']]
    for caption in captions:
        if caption and required_tags.intersection(map(normalized_tag, CAPTION_TAG.findall(caption))):
            return caption
    return None


def read_post(page, shortcode, url, config, log, *, required_tags=None):
    network = PostResponses(shortcode, config['max_comments'])
    page.on('response', network.receive)
    try:
        response = page.goto(url, wait_until='domcontentloaded', timeout=40_000)
        location = urlsplit(page.url)
        check_page_access(page, network)
        if (
            (response and response.status >= 400)
            or location.hostname != 'www.instagram.com'
            or not re.fullmatch(r'/(?:[A-Za-z0-9_.]{1,30}/)?(?:p|reel|reels)/' + re.escape(shortcode) + r'/?', location.path, re.ASCII)
        ):
            raise CollectionError('اینستاگرام صفحهٔ پست را باز نکرد.')
        page.wait_for_timeout(1500)
        if required_tags:
            caption = matching_caption(page, network.fields.get('caption'), required_tags)
            if caption is None:
                return None
            network.fields['caption'] = caption
        for _ in range(3):
            check_page_access(page, network)
            network.read_pending_comments()
            if len(network.comments) >= config['max_comments']:
                break
            if visible_comments(page, 1):
                break
            controls = page.get_by_role('button', name=COMMENT_CONTROL).or_(
                page.get_by_role('link', name=COMMENT_CONTROL)
            ).or_(page.get_by_text(COMMENT_CONTROL)).or_(
                page.locator(
                    'article :is(button, [role="button"]):has(svg[aria-label="Comment"]), '
                    'main :is(button, [role="button"]):has(svg[aria-label="Comment"])'
                )
            )
            more = next((item for item in controls.all() if item.is_visible()), None)
            if more is None:
                break
            try:
                more.click(timeout=2500)
            except TimeoutError:
                break
            page.wait_for_timeout(1200)
            if urlsplit(page.url).path.rstrip('/') != location.path.rstrip('/'):
                break
        check_page_access(page, network)
        network.read_pending_comments()
        comments, expanded, scrolled, stop_reason, visible_count = collect_loaded_comments(
            page, network, config['max_comments'],
        )
        if config.get('post_url'):
            log(f'پنل کامنت: {scrolled} بار اسکرول، {expanded} کنترل نمایش بیشتر باز شد. پایان: {stop_reason}.')
            log(
                f'جزئیات کامنت: {visible_count} مورد از صفحه، {len(network.comments)} مورد از شبکه، '
                f'{network.comment_responses} پاسخ مرتبط با کامنت.'
            )
            panel = visible_comments(page, config['max_comments'], diagnostics=True)
            log(
                f'ساختار پنل: {panel["reply_actions"]} کنترل پاسخ، {panel["permalinks"]} لینک کامنت، '
                f'{panel["unreadable_rows"]} مورد شناسایی‌شده بدون متن قابل خواندن.'
            )
        method = 'browser_network' if network.fields or network.comments else 'browser'
        if not comments and config.get('post_url') and not config.get('background') and network.fields.get('reported_comment_count') != 0:
            log('کامنت خودکار پیدا نشد. تا ۳۰ ثانیه روی آیکون کامنت همان پست در پنجرهٔ اینستاگرام بزنید.')
            page.bring_to_front()
            for _ in range(30):
                page.wait_for_timeout(1000)
                check_page_access(page, network)
                network.read_pending_comments()
                comments = list(network.comments.values())
                if comments:
                    method = 'browser_network'
                    break
                current = urlsplit(page.url)
                if current.hostname == location.hostname and current.path.rstrip('/') in (
                    location.path.rstrip('/'), location.path.rstrip('/') + '/comments',
                ):
                    comments = visible_comments(page, config['max_comments'])
                    if comments:
                        break
        if not comments and network.fields.get('reported_comment_count') != 0:
            log(
                f'کامنت قابل استخراج نبود. {network.json_responses} پاسخ داده و '
                f'{network.comment_responses} پاسخ مرتبط با کامنت شناسایی شد.'
            )
        total_likes = network.fields.get('total_likes')
        if total_likes is None:
            total_likes = extract_total_likes(page)
        if total_likes is None:
            log('تعداد لایک این پست از پاسخ شبکه یا صفحه قابل خواندن نبود.')
        likers = []
        if config['likers']:
            likers = extract_likers(page, url)[:config['max_likers']]
            check_page_access(page, network)
        published = network.fields.get('published_at') or page.evaluate(r"""() => {
            const metadata = document.querySelector('meta[property="article:published_time"], meta[itemprop="datePublished"]');
            if (metadata?.content) return metadata.content;
            const path = location.pathname.replace(/\/$/, '');
            const link = [...document.querySelectorAll('article a[href], main a[href]')].find(a =>
                a.origin === location.origin && a.pathname.replace(/\/$/, '') === path && a.querySelector('time[datetime]')
            );
            return link?.querySelector('time').dateTime || null;
        }""")
        visible_post = visible_post_details(page)
        if not network.fields.get('caption') and visible_post['caption']:
            network.fields['caption'] = visible_post['caption']
        if not network.fields.get('owner') and visible_post['owner']:
            network.fields['owner'] = visible_post['owner']
        if not network.fields.get('caption'):
            log('متن این پست از صفحه یا پاسخ شبکه قابل خواندن نبود.')
        return {
            **network.fields,
            'post_url': url,
            'shortcode': shortcode,
            'media_id': network.fields.get('media_id') or next(iter(network.media_ids), None),
            'published_at': published,
            'scraped_at': datetime.now(timezone.utc).isoformat(),
            'total_likes': total_likes,
            'comments': comments,
            'likers': likers,
            'collection_method': method,
        }
    finally:
        page.remove_listener('response', network.receive)


@contextmanager
def open_instagram_browser(chromium, profile_dir, background, log):
    modes = (True, False) if background else (False,)
    for headless in modes:
        context = chromium.launch_persistent_context(
            str(profile_dir), channel=os.environ.get('DIDBAN_BROWSER_CHANNEL', 'chromium'), headless=headless, locale='en-US',
            viewport={'width': 1366, 'height': 768}, accept_downloads=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            home = page.goto(INSTAGRAM_ORIGIN + '/', wait_until='domcontentloaded', timeout=30_000)
            if home and home.status in (403, 429):
                raise CollectionError(f'اینستاگرام دسترسی را محدود کرد ({home.status}).')
            if urlsplit(page.url).path.startswith(('/challenge', '/checkpoint', '/accounts/suspended')):
                raise CollectionError('اینستاگرام تأیید حساب خواست. وضعیت حساب را در خود اینستاگرام بررسی کنید.')
            if not is_logged_in(page):
                if headless:
                    log('نشست آماده نیست. پنجرهٔ ورود باز می‌شود و این اجرا با پنجرهٔ قابل مشاهده ادامه می‌یابد.')
                    continue
                log('در پنجرهٔ اینستاگرام وارد شوید و در صورت نیاز تأیید حساب را کامل کنید.')
                wait_for_instagram_login(page)
            if headless:
                log('جمع‌آوری در پس‌زمینه با نشست ذخیره‌شده آغاز شد.')
            yield context, page, headless
            return
        finally:
            context.close()


def collect_in_browser(config, save, log, known_posts=()):
    scope = config.get('collection_scope')
    sources = [('profile', name) for name in config['profiles']]
    if scope != 'profile_tags':
        sources += [('hashtag', name) for name in config['hashtags']]
    required_tags = {normalized_tag(tag) for tag in config['hashtags']} if scope == 'profile_tags' else None
    saved_any = False
    found_links = False
    skipped = set()
    checked = set()
    unresolved_in_a_row = 0
    profile_dir = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Didban' / 'instagram-profile'
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            with open_instagram_browser(playwright.chromium, profile_dir, config.get('background', False), log) as (context, page, background):
                run_config = {**config, 'background': background}
                post_page = context.new_page()
                if config.get('post_url'):
                    shortcode, url = parse_post_url(config['post_url'])
                    log(f'نشست مرورگر آماده است. پست {shortcode} بررسی می‌شود.')
                    row = read_post(post_page, shortcode, url, run_config, log)
                    save({**row, 'source': shortcode, 'source_type': 'post'})
                    log(f'پست ذخیره شد. {len(row["comments"])} کامنت ثبت شد.')
                    return
                log('نشست مرورگر آماده است. صفحهٔ منابع بررسی می‌شود.')
                source_responses = PostResponses('', 0)
                page.on('response', source_responses.receive)
                for kind, name in sources:
                    if kind == 'profile':
                        log(f'بررسی پیج: @{name}')
                    else:
                        log(f'جست‌وجوی #{name}' + (' در دیسکاور' if scope == 'discover' else ''))
                    links = find_post_links(
                        page, kind, name, config['max_posts'], config['scrolls'],
                        check_access=lambda: check_page_access(page, source_responses),
                        discover=scope == 'discover',
                    )
                    check_page_access(page, source_responses)
                    if not links:
                        log('لینک پستی در صفحهٔ این منبع پیدا نشد.')
                    else:
                        found_links = True
                        log(f'{len(links)} لینک پست برای بررسی پیدا شد.')
                    for shortcode, url in links.items():
                        if shortcode in checked:
                            continue
                        checked.add(shortcode)
                        if shortcode in known_posts and not config.get('refresh_posts'):
                            skipped.add(shortcode)
                            continue
                        row = read_post(post_page, shortcode, url, run_config, log, required_tags=required_tags)
                        if row is None:
                            log(f'تگ موردنظر در کپشن قابل‌خواندن پست {shortcode} پیدا نشد.')
                            continue
                        save({**row, 'source': name, 'source_type': kind})
                        saved_any = True
                        log(f'پست {shortcode} ذخیره شد. {len(row["comments"])} کامنت ثبت شد.')
                        if row['comments'] or row.get('reported_comment_count') == 0:
                            unresolved_in_a_row = 0
                        else:
                            unresolved_in_a_row += 1
                            if unresolved_in_a_row >= 3:
                                raise CollectionError(
                                    'کامنت سه پست پیاپی قابل خواندن نبود. اجرا متوقف شد و پست‌های ثبت‌شده در نتایج هستند.'
                                )
    except Error:
        raise CollectionError('مرورگر نتوانست صفحهٔ اینستاگرام را باز یا پردازش کند. نصب و دسترسی مرورگر را بررسی کنید.') from None
    if skipped:
        log(f'{len(skipped)} پست قبلاً ثبت شده بود و دوباره باز نشد.')
    if not saved_any and not skipped:
        if scope == 'profile_tags':
            if not found_links:
                raise CollectionError('لینک پستی در پیج‌های انتخاب‌شده پیدا نشد. دسترسی و وضعیت صفحهٔ پیج را بررسی کنید.')
            raise CollectionError('در پست‌های بررسی‌شدهٔ پیج‌ها، کپشنی با تگ‌های واردشده پیدا نشد.')
        if scope == 'discover':
            raise CollectionError('دیسکاور برای تگ‌های واردشده پستی نشان نداد.')
        raise CollectionError('پستی در صفحات پیج یا هشتگ پیدا نشد. همان منابع را در اینستاگرام بررسی کنید.')
