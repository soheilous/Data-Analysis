"""Read-only metrics computed from a project's merged posts.

Everything here is a pure function of the stored post payloads, so it works for
posts collected by any method (direct, browser, instagrapi) and needs no extra
tables. Follower counts are not collected, so engagement is reported as
absolute interactions (likes + comments) rather than a follower-based rate.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

TEHRAN = ZoneInfo('Asia/Tehran')
# Instagram tags may contain letters/digits/underscore in any script, including
# Persian letters and the zero-width non-joiner used inside Persian words.
HASHTAG = re.compile(r'#([\w‌]+)')
WORD = re.compile(r'[^\W\d_][\w‌]*')
PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
COMPACT = re.compile(r'^(\d+(?:\.\d+)?)([KMB])$', re.IGNORECASE)
STOPWORDS = {
    # Persian
    'و', 'در', 'به', 'از', 'که', 'این', 'را', 'با', 'است', 'برای', 'آن', 'یک', 'هم', 'تا', 'ما',
    'من', 'شما', 'او', 'هر', 'اما', 'یا', 'بر', 'نه', 'چه', 'رو', 'هست', 'بود', 'شد', 'می', 'های',
    'ها', 'دیگه', 'دیگر', 'خیلی', 'کنید', 'کنم', 'کرد', 'کردن', 'باشه', 'بی', 'اگه', 'اگر', 'چرا',
    'کجا', 'کی', 'چی', 'همه', 'ولی', 'نیست', 'داره', 'دارید', 'دارم', 'میشه', 'اون', 'اینو', 'منم',
    # English
    'the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'on', 'for', 'is', 'it', 'this', 'that', 'i',
    'you', 'we', 'my', 'your', 'me', 'be', 'are', 'was', 'with', 'so', 'at', 'just', 'not', 'but',
}
WEEKDAYS = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']


def number(value):
    """Likes arrive as int, numeric string, or Instagram's compact form (1.2K)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    text = str(value).strip().translate(PERSIAN_DIGITS).replace(',', '').replace('٬', '')
    if text.isdecimal():
        return int(text)
    match = COMPACT.match(text)
    if match:
        return int(float(match[1]) * {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}[match[2].upper()])
    return None


def moment(value):
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo('UTC'))
    return parsed.astimezone(TEHRAN)


def hashtags(text):
    return list(dict.fromkeys(tag.strip('‌').casefold() for tag in HASHTAG.findall(text or '') if tag.strip('‌')))


def words(text):
    text = HASHTAG.sub(' ', re.sub(r'@[\w.]+', ' ', text or ''))
    for word in WORD.findall(text):
        word = word.strip('‌').casefold()
        if len(word) > 1 and word not in STOPWORDS:
            yield word


def average(total, count):
    return round(total / count, 1) if count else 0


def post_owner(post):
    return post.get('owner') or (post.get('source') if post.get('source_type') == 'profile' else None)


def week_start(day):
    # Iranian weeks start on Saturday.
    return day - timedelta(days=(day.weekday() + 2) % 7)


def project_analytics(posts, top=10):
    rows = []
    for post in posts:
        likes = number(post.get('total_likes'))
        collected = post.get('comments') or []
        reported = number(post.get('reported_comment_count'))
        comments = max(len(collected), reported or 0)
        rows.append({
            'post': post,
            'likes': likes,
            'comments': comments,
            'engagement': (likes or 0) + comments,
            'published': moment(post.get('published_at')),
            'tags': hashtags(post.get('caption')),
            'owner': post_owner(post),
        })

    with_likes = [row for row in rows if row['likes'] is not None]
    total_likes = sum(row['likes'] for row in with_likes)
    total_comments = sum(row['comments'] for row in rows)
    collected_comments = [
        (row, comment) for row in rows for comment in (row['post'].get('comments') or [])
    ]
    dated = sorted((row for row in rows if row['published']), key=lambda row: row['published'])

    summary = {
        'posts': len(rows),
        'posts_with_likes': len(with_likes),
        'total_likes': total_likes,
        'total_comments': total_comments,
        'collected_comments': len(collected_comments),
        'unique_commenters': len({(c.get('username') or '').casefold() for _, c in collected_comments if c.get('username')}),
        'avg_likes': average(total_likes, len(with_likes)),
        'avg_comments': average(total_comments, len(rows)),
        'avg_engagement': average(sum(row['engagement'] for row in rows), len(rows)),
        'first_post_at': dated[0]['published'].isoformat() if dated else None,
        'last_post_at': dated[-1]['published'].isoformat() if dated else None,
    }
    if len(dated) > 1:
        span = (dated[-1]['published'] - dated[0]['published']).total_seconds() / 86400
        summary['posts_per_week'] = round(len(dated) / max(span, 1) * 7, 1)
    else:
        summary['posts_per_week'] = None

    top_posts = [{
        'post_url': row['post'].get('post_url'),
        'shortcode': row['post'].get('shortcode'),
        'owner': row['owner'],
        'caption': (row['post'].get('caption') or '')[:200],
        'published_at': row['post'].get('published_at'),
        'likes': row['likes'],
        'comments': row['comments'],
        'engagement': row['engagement'],
    } for row in sorted(rows, key=lambda row: row['engagement'], reverse=True)[:top]]

    # Posting frequency and engagement over time, by Tehran calendar day.
    by_day = defaultdict(lambda: {'posts': 0, 'likes': 0, 'comments': 0, 'engagement': 0})
    weekdays = [{'day': name, 'posts': 0, 'engagement': 0} for name in WEEKDAYS]
    hours = [{'hour': hour, 'posts': 0, 'engagement': 0} for hour in range(24)]
    for row in dated:
        day = by_day[row['published'].date().isoformat()]
        day['posts'] += 1
        day['likes'] += row['likes'] or 0
        day['comments'] += row['comments']
        day['engagement'] += row['engagement']
        weekday = weekdays[(row['published'].weekday() + 2) % 7]
        weekday['posts'] += 1
        weekday['engagement'] += row['engagement']
        hour = hours[row['published'].hour]
        hour['posts'] += 1
        hour['engagement'] += row['engagement']
    for bucket in (*weekdays, *hours):
        bucket['avg_engagement'] = average(bucket.pop('engagement'), bucket['posts'])
    timeline = [{'date': key, **value} for key, value in sorted(by_day.items())]

    weekly = defaultdict(int)
    for row in dated:
        weekly[week_start(row['published'].date()).isoformat()] += 1

    # Hashtags: usage, engagement, and weekly usage of the most used tags.
    tag_stats = defaultdict(lambda: {'posts': 0, 'engagement': 0})
    tag_weeks = defaultdict(Counter)
    for row in rows:
        for tag in row['tags']:
            tag_stats[tag]['posts'] += 1
            tag_stats[tag]['engagement'] += row['engagement']
            if row['published']:
                tag_weeks[tag][week_start(row['published'].date()).isoformat()] += 1
    tags = sorted(({
        'tag': tag,
        'posts': value['posts'],
        'avg_engagement': average(value['engagement'], value['posts']),
    } for tag, value in tag_stats.items()), key=lambda item: (-item['posts'], -item['avg_engagement'], item['tag']))[:top * 2]
    weeks = sorted(weekly)
    tag_trends = [{
        'tag': item['tag'],
        'weeks': [{'week': week, 'posts': tag_weeks[item['tag']].get(week, 0)} for week in weeks],
    } for item in tags[:5]]

    # Comments: volume over time, most active commenters, and common terms.
    comment_days = Counter()
    commenters = Counter()
    terms = Counter()
    for _, comment in collected_comments:
        when = moment(comment.get('time'))
        if when:
            comment_days[when.date().isoformat()] += 1
        if comment.get('username'):
            commenters[comment['username']] += 1
        terms.update(set(words(comment.get('text'))))

    accounts = defaultdict(lambda: {'posts': 0, 'likes': 0, 'comments': 0, 'engagement': 0})
    for row in rows:
        account = accounts[row['owner'] or '—']
        account['posts'] += 1
        account['likes'] += row['likes'] or 0
        account['comments'] += row['comments']
        account['engagement'] += row['engagement']
    owners = sorted(({
        'owner': owner, **value, 'avg_engagement': average(value['engagement'], value['posts']),
    } for owner, value in accounts.items()), key=lambda item: -item['engagement'])[:top * 2]

    return {
        'summary': summary,
        'top_posts': top_posts,
        'posting': {
            'timeline': timeline,
            'weekly': [{'week': week, 'posts': weekly[week]} for week in weeks],
            'weekdays': weekdays,
            'hours': hours,
        },
        'hashtags': {'top': tags, 'trends': tag_trends},
        'comments': {
            'timeline': [{'date': day, 'comments': count} for day, count in sorted(comment_days.items())],
            'top_commenters': [{'username': name, 'comments': count} for name, count in commenters.most_common(top)],
            'top_terms': [{'term': term, 'count': count} for term, count in terms.most_common(top * 2) if count > 1],
        },
        'accounts': owners,
    }
