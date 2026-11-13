"""Project storage and merging for Instagram collection results."""

import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
import re
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def post_key(row):
    path = urlsplit(row.get('post_url') or '').path
    match = re.fullmatch(r'/(?:p|reels?)/([A-Za-z0-9_-]+)/?', path)
    return match[1] if match else row.get('shortcode') or row.get('media_id')


def merge_post(previous, incoming):
    merged = dict(previous)
    merged.update({key: value for key, value in incoming.items()
                   if value is not None and value != '' and key not in ('comments', 'likers')})
    merged['first_collected_at'] = previous.get('first_collected_at') or previous.get('scraped_at') or incoming.get('scraped_at')
    merged['shortcode'] = post_key(incoming)
    comments = list(previous.get('comments', []))
    available = set(range(len(comments)))
    added = []
    for comment in incoming.get('comments', []):
        identity = comment.get('comment_id')
        match = next((i for i, old in enumerate(comments)
                      if identity and identity == old.get('comment_id')), None)
        if match is None:
            for i in sorted(available):
                old = comments[i]
                if identity and old.get('comment_id'):
                    continue
                if (comment['username'].casefold() == old['username'].casefold()
                        and comment['text'].strip() == old['text'].strip()
                        and (not comment.get('time') or not old.get('time') or comment['time'] == old['time'])):
                    match = i
                    break
        if match is None:
            comments.append(comment)
            added.append(comment)
        else:
            available.discard(match)
            comments[match] = {**comments[match], **{k: v for k, v in comment.items() if v is not None}}
    merged['comments'] = comments
    merged['likers'] = list(dict.fromkeys([*previous.get('likers', []), *incoming.get('likers', [])]))
    return merged, added


def store_post(connection, project_id, row):
    key = post_key(row)
    if not key:
        return None
    old = connection.execute(
        'SELECT payload FROM project_posts WHERE project_id=? AND post_key=?', (project_id, key),
    ).fetchone()
    merged, added = merge_post(json.loads(old[0]) if old else {}, row)
    connection.execute(
        '''INSERT INTO project_posts VALUES (?,?,?)
           ON CONFLICT(project_id,post_key) DO UPDATE SET payload=excluded.payload''',
        (project_id, key, json.dumps(merged, ensure_ascii=False)),
    )
    return {**row, 'shortcode': key, 'comments': added, 'new_post': not bool(old)} if not old or added else None


def initialize_projects(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, config TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
    connection.execute('CREATE TABLE IF NOT EXISTS project_posts(project_id TEXT, post_key TEXT, payload TEXT, PRIMARY KEY(project_id,post_key))')
    columns = {row[1] for row in connection.execute('PRAGMA table_info(runs)')}
    if 'project_id' in columns:
        return
    connection.execute('ALTER TABLE runs ADD COLUMN project_id TEXT')
    connection.execute('ALTER TABLE runs ADD COLUMN started_at TEXT')
    connection.execute('CREATE INDEX runs_project ON runs(project_id)')
    by_title = {}
    for run_id, raw in connection.execute('SELECT id,config FROM runs ORDER BY rowid').fetchall():
        config = json.loads(raw)
        if config.get('post_url') or config.get('demo'):
            continue
        if not (config.get('profiles') or config.get('target') or config.get('hashtags')):
            continue
        title = (config.get('title') or config.get('target') or 'پروژهٔ قدیمی').strip()
        project_id = by_title.setdefault(title, uuid.uuid4().hex)
        config.update(title=title, method='browser')
        for key in ('login_username', 'login_password', 'verification_code'):
            config.pop(key, None)
        stamp = now()
        connection.execute(
            '''INSERT INTO projects VALUES (?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET config=excluded.config,updated_at=excluded.updated_at''',
            (project_id, json.dumps(config, ensure_ascii=False), stamp, stamp),
        )
        connection.execute('UPDATE runs SET project_id=? WHERE id=?', (project_id, run_id))
        for (payload,) in connection.execute('SELECT payload FROM results WHERE run=?', (run_id,)):
            store_post(connection, project_id, json.loads(payload))
