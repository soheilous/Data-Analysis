"""Keep collection at the pace of one modest, ordinary Instagram user.

Every collector shares the same rules:

* a random pause before each request, a longer one before each post, and a
  long break every few posts, so requests never arrive in tight bursts;
* a per-account daily budget of requests and posts;
* a cooldown after Instagram signals a limit (429, feedback_required,
  challenge, suspension). While it lasts, runs for that account do not start.

This lowers the chance of an account restriction. It does not remove it:
automated collection is against Instagram's terms, and a cautious pace is the
only lever this module uses. It never rotates accounts, proxies or devices.

Limits can be tuned with environment variables (see ``Limits.from_env``).
State lives in ``account-limits.json`` under the Didban state folder.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import threading
import time

from direct_scraper import CollectionError


COOLDOWN_HOURS = {
    'rate_limit': 6,
    'feedback': 24,
    'challenge': 24,
    'suspended': 72,
}
COOLDOWN_REASONS = {
    'rate_limit': 'اینستاگرام تعداد درخواست‌ها را محدود کرد (۴۲۹)',
    'feedback': 'اینستاگرام فعالیت حساب را محدود کرد (feedback_required)',
    'challenge': 'اینستاگرام تأیید امنیتی حساب را خواست',
    'suspended': 'اینستاگرام تعلیق یا محدودیت حساب را اعلام کرد',
}
_state_lock = threading.Lock()


class AccountRestricted(CollectionError):
    """Instagram signalled a limit; the account is put on cooldown."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


def state_dir():
    override = os.environ.get('DIDBAN_STATE_DIR')
    root = Path(override) if override else Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Didban'
    root.mkdir(parents=True, exist_ok=True)
    return root


def account_key(method, username=''):
    """A stable key that does not store the username in clear text."""
    name = (username or '').strip().casefold()
    if not name:
        return method
    return method + '-' + hashlib.sha256(name.encode()).hexdigest()[:16]


def session_path(method, username):
    folder = state_dir() / 'sessions'
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    return folder / (account_key(method, username) + '.json')


def protect_file(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _env_number(name, default, kind=float):
    try:
        value = kind(os.environ.get(name, default))
    except ValueError:
        return default
    return value if value >= 0 else default


@dataclass(frozen=True)
class Limits:
    daily_requests: int = 600
    daily_posts: int = 120
    request_pause: tuple = (3.0, 8.0)
    post_pause: tuple = (10.0, 25.0)
    source_pause: tuple = (30.0, 60.0)
    break_every_posts: int = 12
    break_pause: tuple = (90.0, 240.0)

    @classmethod
    def from_env(cls):
        scale = _env_number('DIDBAN_PAUSE_SCALE', 1.0)
        base = cls()

        def scaled(pair):
            return (pair[0] * scale, pair[1] * scale)

        return cls(
            daily_requests=_env_number('DIDBAN_DAILY_REQUESTS', base.daily_requests, int),
            daily_posts=_env_number('DIDBAN_DAILY_POSTS', base.daily_posts, int),
            request_pause=scaled(base.request_pause),
            post_pause=scaled(base.post_pause),
            source_pause=scaled(base.source_pause),
            break_every_posts=base.break_every_posts,
            break_pause=scaled(base.break_pause),
        )


def _now():
    return datetime.now(timezone.utc)


def _today():
    return datetime.now().date().isoformat()


def _load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _store(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    os.replace(temporary, path)


def _local_time(moment):
    return moment.astimezone().strftime('%Y-%m-%d %H:%M')


class Throttle:
    """Pacing, daily budget and cooldown for one Instagram account."""

    def __init__(self, key, log=lambda message: None, *, limits=None, sleep=time.sleep, rng=None):
        self.key = key
        self.log = log
        self.limits = limits or Limits.from_env()
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.path = state_dir() / 'account-limits.json'
        self.posts_this_run = 0

    def _update(self, change):
        with _state_lock:
            data = _load(self.path)
            entry = data.get(self.key, {})
            if entry.get('day') != _today():
                entry = {'day': _today(), 'requests': 0, 'posts': 0,
                         **{k: entry[k] for k in ('cooldown_until', 'cooldown_kind') if k in entry}}
            result = change(entry)
            data[self.key] = entry
            _store(self.path, data)
            return result

    def _pause(self, bounds):
        low, high = bounds
        if high > 0:
            self.sleep(self.rng.uniform(low, high))

    def check(self):
        """Refuse to start while the account is cooling down or over budget."""
        entry = self._update(lambda entry: dict(entry))
        until = entry.get('cooldown_until')
        if until and datetime.fromisoformat(until) > _now():
            reason = COOLDOWN_REASONS.get(entry.get('cooldown_kind'), 'اینستاگرام محدودیت اعلام کرد')
            raise CollectionError(
                f'{reason}. برای کم کردن خطر بن، اجرا برای این حساب تا {_local_time(datetime.fromisoformat(until))} '
                'متوقف است. در این مدت با حساب کار عادی (و نه خودکار) انجام دهید.'
            )
        self._check_budget(entry)

    def _check_budget(self, entry):
        if entry['requests'] >= self.limits.daily_requests:
            raise CollectionError(
                f'سقف روزانهٔ {self.limits.daily_requests} درخواست برای این حساب پر شد. فردا ادامه دهید.'
            )
        if entry['posts'] >= self.limits.daily_posts:
            raise CollectionError(
                f'سقف روزانهٔ {self.limits.daily_posts} پست برای این حساب پر شد. فردا ادامه دهید.'
            )

    def before_request(self):
        def count(entry):
            self._check_budget(entry)
            entry['requests'] += 1
        self._update(count)
        self._pause(self.limits.request_pause)

    def before_post(self):
        def count(entry):
            self._check_budget(entry)
            entry['posts'] += 1
        self._update(count)
        if self.posts_this_run and self.posts_this_run % self.limits.break_every_posts == 0:
            self.log('استراحت کوتاه برای حفظ سرعت عادی حساب.')
            self._pause(self.limits.break_pause)
        elif self.posts_this_run:
            self._pause(self.limits.post_pause)
        self.posts_this_run += 1

    def between_sources(self):
        self._pause(self.limits.source_pause)

    def restrict(self, kind, prefix=''):
        """Record a cooldown and return the error to raise."""
        until = _now() + timedelta(hours=COOLDOWN_HOURS[kind])

        def mark(entry):
            previous = entry.get('cooldown_until')
            if not previous or datetime.fromisoformat(previous) < until:
                entry['cooldown_until'] = until.isoformat()
                entry['cooldown_kind'] = kind
        self._update(mark)
        return AccountRestricted(
            f'{prefix}{COOLDOWN_REASONS[kind]}. اجرا متوقف شد و این حساب تا {_local_time(until)} '
            'جمع‌آوری خودکار انجام نمی‌دهد.',
            kind,
        )


def account_status(key, limits=None):
    """Today's usage and any cooldown for one account, without changing state."""
    limits = limits or Limits.from_env()
    with _state_lock:
        entry = _load(state_dir() / 'account-limits.json').get(key, {})
    today = entry.get('day') == _today()
    status = {
        'requests_used': entry.get('requests', 0) if today else 0,
        'requests_limit': limits.daily_requests,
        'posts_used': entry.get('posts', 0) if today else 0,
        'posts_limit': limits.daily_posts,
        'cooldown_until': None,
        'cooldown_reason': None,
    }
    until = entry.get('cooldown_until')
    if until and datetime.fromisoformat(until) > _now():
        status['cooldown_until'] = until
        status['cooldown_reason'] = COOLDOWN_REASONS.get(entry.get('cooldown_kind'), 'اینستاگرام محدودیت اعلام کرد')
    return status


def classify_restriction(error):
    """Map an upstream error (any library) to a cooldown kind, or None."""
    name = type(error).__name__
    detail = str(error).casefold()
    if name in ('AccountSuspended',) or 'suspended' in detail:
        return 'suspended'
    if name in ('ChallengeRequired', 'CaptchaChallengeRequired', 'RecaptchaChallengeForm',
                'ChallengeSelfieCaptcha', 'ChallengeRedirection') or any(
            marker in detail for marker in ('checkpoint_required', 'checkpoint required', 'challenge_required')):
        return 'challenge'
    if name in ('FeedbackRequired', 'SignupSpamError') or 'feedback_required' in detail:
        return 'feedback'
    if name in ('TooManyRequestsException', 'PleaseWaitFewMinutes', 'RateLimitError') or (
            '429' in detail and ('too many' in detail or 'fail, 429' in detail)):
        return 'rate_limit'
    return None
