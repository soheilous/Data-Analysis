"""Project storage and merging for Instagram collection results.

Posts and comments are stored in normalized tables:

* ``posts`` holds one row per post. Project posts are unique per
  ``(project_id, post_key)`` and are merged across runs. Posts from runs that
  do not belong to a project have ``project_id`` NULL and are scoped to their
  ``run_id``.
* ``comments`` holds one row per comment, linked to its post. ``run_id`` is the
  run that first collected the comment.
* ``run_posts`` records each time a run saw a post, with that run's own
  ``scraped_at`` and ``total_likes``. ``in_results`` marks the rows that make up
  the run's result list (a new post, or an existing post with new comments).

Fields without a dedicated column are kept in each row's ``extra`` JSON object,
so the dictionaries returned to the API keep the same shape as before.
"""

import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
import re
import uuid

SCHEMA_VERSION = 1

POST_COLUMNS = (
    'post_key', 'post_url', 'shortcode', 'media_id', 'owner', 'caption', 'source', 'source_type',
    'published_at', 'first_collected_at', 'scraped_at', 'total_likes', 'reported_comment_count',
    'collection_method',
)
COMMENT_COLUMNS = ('comment_id', 'username', 'text', 'time', 'likes')
# Keys that only describe a row in a run's result list, never a stored post.
RESULT_ONLY_KEYS = ('new_post',)


def now():
    return datetime.now(timezone.utc).isoformat()


def post_key(row):
    path = urlsplit(row.get('post_url') or '').path
    match = re.fullmatch(r'/(?:p|reels?)/([A-Za-z0-9_-]+)/?', path)
    return match[1] if match else row.get('shortcode') or row.get('media_id')


def same_comment_text(comment, old):
    return (comment['username'].casefold() == old['username'].casefold()
            and comment['text'].strip() == old['text'].strip()
            and (not comment.get('time') or not old.get('time') or comment['time'] == old['time']))


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
                if same_comment_text(comment, old):
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


# --- schema -----------------------------------------------------------------

def create_tables(connection):
    # Statements run one at a time: executescript would commit the caller's transaction.
    statements = '''
        CREATE TABLE IF NOT EXISTS posts(
            id INTEGER PRIMARY KEY,
            project_id TEXT,
            run_id TEXT,
            post_key TEXT,
            post_url TEXT,
            shortcode TEXT,
            media_id TEXT,
            owner TEXT,
            caption TEXT,
            source TEXT,
            source_type TEXT,
            published_at TEXT,
            first_collected_at TEXT,
            scraped_at TEXT,
            total_likes INTEGER,
            reported_comment_count INTEGER,
            collection_method TEXT,
            likers TEXT NOT NULL DEFAULT '[]',
            extra TEXT NOT NULL DEFAULT '{}'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS posts_project_key ON posts(project_id, post_key)
            WHERE project_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS posts_run_key ON posts(run_id, post_key) WHERE project_id IS NULL;
        CREATE INDEX IF NOT EXISTS posts_owner ON posts(owner);
        CREATE TABLE IF NOT EXISTS comments(
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            run_id TEXT,
            position INTEGER NOT NULL,
            comment_id TEXT,
            username TEXT,
            text TEXT,
            time TEXT,
            likes INTEGER,
            extra TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS comments_post ON comments(post_id, position);
        CREATE INDEX IF NOT EXISTS comments_run ON comments(run_id);
        CREATE INDEX IF NOT EXISTS comments_username ON comments(username);
        CREATE TABLE IF NOT EXISTS run_posts(
            run_id TEXT NOT NULL,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            new_post INTEGER NOT NULL,
            in_results INTEGER NOT NULL,
            scraped_at TEXT,
            total_likes INTEGER,
            PRIMARY KEY(run_id, post_id)
        );
        CREATE INDEX IF NOT EXISTS run_posts_post ON run_posts(post_id);
    '''
    for statement in statements.split(';'):
        if statement.strip():
            connection.execute(statement)


def table_exists(connection, name):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


# --- row conversion ---------------------------------------------------------

def _split(values, columns, skip=()):
    core = {column: values.get(column) for column in columns}
    extra = {key: value for key, value in values.items()
             if key not in columns and key not in skip and value is not None}
    return core, json.dumps(extra, ensure_ascii=False)


def _post_dict(row):
    post = json.loads(row['extra'])
    post.update({column: row[column] for column in POST_COLUMNS
                 if column != 'post_key' and row[column] is not None})
    post['likers'] = json.loads(row['likers'])
    post['comments'] = []
    return post


def _comment_dict(row):
    comment = json.loads(row['extra'])
    comment.update({column: row[column] for column in COMMENT_COLUMNS if row[column] is not None})
    return comment


def _rows(connection, sql, params):
    cursor = connection.execute(sql, params)
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, values)) for values in cursor]


def _load_post(connection, post_id):
    post = _post_dict(_rows(connection, 'SELECT * FROM posts WHERE id=?', (post_id,))[0])
    comments = _rows(connection, 'SELECT * FROM comments WHERE post_id=? ORDER BY position', (post_id,))
    post['comments'] = [_comment_dict(row) for row in comments]
    return post, [row['id'] for row in comments]


def _write_post(connection, post_id, project_id, run_id, post, key):
    core, extra = _split(post, POST_COLUMNS, skip=('comments', 'likers', *RESULT_ONLY_KEYS))
    core['post_key'] = key
    values = [*core.values(), json.dumps(post.get('likers', []), ensure_ascii=False), extra]
    names = [*core, 'likers', 'extra']
    if post_id is None:
        cursor = connection.execute(
            f'INSERT INTO posts(project_id,run_id,{",".join(names)}) VALUES ({",".join("?" * (len(names) + 2))})',
            (project_id, run_id, *values),
        )
        return cursor.lastrowid
    connection.execute(
        f'UPDATE posts SET {",".join(name + "=?" for name in names)} WHERE id=?', (*values, post_id),
    )
    return post_id


def _insert_comment(connection, post_id, run_id, position, comment):
    core, extra = _split(comment, COMMENT_COLUMNS)
    connection.execute(
        f'INSERT INTO comments(post_id,run_id,position,{",".join(core)},extra) VALUES (?,?,?,{",".join("?" * len(core))},?)',
        (post_id, run_id, position, *core.values(), extra),
    )


def _update_comment(connection, comment_row_id, comment):
    core, extra = _split(comment, COMMENT_COLUMNS)
    connection.execute(
        f'UPDATE comments SET {",".join(name + "=?" for name in core)},extra=? WHERE id=?',
        (*core.values(), extra, comment_row_id),
    )


def _record_run(connection, run_id, post_id, new_post, in_results, row):
    connection.execute(
        '''INSERT INTO run_posts(run_id,post_id,new_post,in_results,scraped_at,total_likes) VALUES (?,?,?,?,?,?)
           ON CONFLICT(run_id,post_id) DO UPDATE SET
               in_results=MAX(in_results, excluded.in_results),
               scraped_at=COALESCE(excluded.scraped_at, scraped_at),
               total_likes=COALESCE(excluded.total_likes, total_likes)''',
        (run_id, post_id, int(new_post), int(in_results), row.get('scraped_at'), row.get('total_likes')),
    )


# --- writes -----------------------------------------------------------------

def _find_post(connection, project_id, run_id, key):
    if not key:
        return None
    if project_id:
        found = connection.execute(
            'SELECT id FROM posts WHERE project_id=? AND post_key=?', (project_id, key),
        ).fetchone()
    else:
        found = connection.execute(
            'SELECT id FROM posts WHERE project_id IS NULL AND run_id=? AND post_key=?', (run_id, key),
        ).fetchone()
    return found[0] if found else None


def save_post(connection, run_id, project_id, row):
    """Merge one collected post into storage.

    Project posts are merged with what earlier runs of the project collected.
    Returns True when the post belongs in this run's results (it is new, or it
    gained comments), which is when it would have been written before.
    """
    key = post_key(row)
    if project_id and not key:
        return False
    post_id = _find_post(connection, project_id, run_id, key)
    previous, comment_ids = _load_post(connection, post_id) if post_id else ({}, [])
    merged, added = merge_post(previous, row)
    post_id = _write_post(connection, post_id, project_id, run_id, merged, key)
    for position, comment in enumerate(merged['comments']):
        if position >= len(comment_ids):
            _insert_comment(connection, post_id, run_id, position, comment)
        elif comment != previous['comments'][position]:
            _update_comment(connection, comment_ids[position], comment)
    in_results = not previous or bool(added)
    _record_run(connection, run_id, post_id, not previous, in_results, row)
    return in_results


def delete_run_data(connection, run_id):
    """Remove a run's own results. Merged project posts and comments are kept."""
    standalone = 'SELECT id FROM posts WHERE project_id IS NULL AND run_id=?'
    connection.execute(f'DELETE FROM comments WHERE post_id IN ({standalone})', (run_id,))
    connection.execute(f'DELETE FROM run_posts WHERE post_id IN ({standalone})', (run_id,))
    connection.execute('DELETE FROM posts WHERE project_id IS NULL AND run_id=?', (run_id,))
    connection.execute('DELETE FROM run_posts WHERE run_id=?', (run_id,))
    connection.execute('UPDATE comments SET run_id=NULL WHERE run_id=?', (run_id,))
    connection.execute('UPDATE posts SET run_id=NULL WHERE run_id=?', (run_id,))
    if table_exists(connection, 'results_legacy'):
        connection.execute('DELETE FROM results_legacy WHERE run=?', (run_id,))


def delete_project_data(connection, project_id):
    posts = 'SELECT id FROM posts WHERE project_id=?'
    runs = 'SELECT id FROM runs WHERE project_id=?'
    for run_id, in connection.execute(runs, (project_id,)).fetchall():
        delete_run_data(connection, run_id)
    connection.execute(f'DELETE FROM comments WHERE post_id IN ({posts})', (project_id,))
    connection.execute(f'DELETE FROM run_posts WHERE post_id IN ({posts})', (project_id,))
    connection.execute('DELETE FROM posts WHERE project_id=?', (project_id,))
    if table_exists(connection, 'project_posts_legacy'):
        connection.execute('DELETE FROM project_posts_legacy WHERE project_id=?', (project_id,))


# --- reads ------------------------------------------------------------------

def _attach_comments(posts, comment_rows):
    for row in comment_rows:
        posts[row['post_id']]['comments'].append(_comment_dict(row))


def project_posts(connection, project_id):
    """All merged posts of a project, most recently first collected first."""
    rows = _rows(connection, 'SELECT * FROM posts WHERE project_id=? ORDER BY id DESC', (project_id,))
    posts = {row['id']: _post_dict(row) for row in rows}
    _attach_comments(posts, _rows(connection, '''
        SELECT comments.* FROM comments JOIN posts ON posts.id=comments.post_id
        WHERE posts.project_id=? ORDER BY comments.post_id, comments.position''', (project_id,)))
    return list(posts.values())


def run_posts(connection, run_id):
    """A run's result list: posts it added or that gained comments, with only that run's comments."""
    rows = _rows(connection, '''
        SELECT posts.*, run_posts.new_post AS run_new_post,
               run_posts.scraped_at AS run_scraped_at, run_posts.total_likes AS run_total_likes
        FROM run_posts JOIN posts ON posts.id=run_posts.post_id
        WHERE run_posts.run_id=? AND run_posts.in_results ORDER BY run_posts.rowid''', (run_id,))
    posts = {}
    for row in rows:
        post = _post_dict(row)
        if row['run_scraped_at'] is not None:
            post['scraped_at'] = row['run_scraped_at']
        if row['run_total_likes'] is not None:
            post['total_likes'] = row['run_total_likes']
        post['new_post'] = bool(row['run_new_post'])
        posts[row['id']] = post
    _attach_comments(posts, _rows(connection, '''
        SELECT comments.* FROM comments JOIN run_posts ON run_posts.post_id=comments.post_id
        WHERE run_posts.run_id=? AND run_posts.in_results AND comments.run_id=?
        ORDER BY comments.post_id, comments.position''', (run_id, run_id)))
    return list(posts.values())


def run_counts(connection):
    """Posts first collected and comments first collected per run."""
    counts = {}
    for run_id, posts in connection.execute(
            'SELECT run_id, SUM(new_post) FROM run_posts WHERE in_results GROUP BY run_id'):
        counts[run_id] = {'posts_count': posts or 0, 'comments_count': 0}
    for run_id, comments in connection.execute(
            'SELECT run_id, COUNT(*) FROM comments WHERE run_id IS NOT NULL GROUP BY run_id'):
        counts.setdefault(run_id, {'posts_count': 0, 'comments_count': 0})['comments_count'] = comments
    return counts


def completed_post_keys(connection, project_id):
    """Project posts that do not need to be opened again: they have comments or none exist."""
    return {key for key, in connection.execute('''
        SELECT post_key FROM posts WHERE project_id=? AND post_key IS NOT NULL
          AND (reported_comment_count=0 OR EXISTS (SELECT 1 FROM comments WHERE comments.post_id=posts.id))''',
        (project_id,))}


# --- migrations -------------------------------------------------------------

def _assign_legacy_projects(connection):
    """Group runs from before projects existed into projects by title."""
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


def _link_result_comments(connection, run_id, post_id, comments):
    stored = _rows(connection, 'SELECT * FROM comments WHERE post_id=? ORDER BY position', (post_id,))
    for comment in comments:
        identity = comment.get('comment_id')
        match = next((row for row in stored if row['run_id'] is None
                      and identity and identity == row['comment_id']), None)
        if match is None:
            match = next((row for row in stored if row['run_id'] is None
                          and not (identity and row['comment_id'])
                          and same_comment_text(comment, _comment_dict(row))), None)
        if match is None:
            _insert_comment(connection, post_id, run_id, len(stored), comment)
            stored.append({'id': None, 'run_id': run_id})
        else:
            match['run_id'] = run_id
            connection.execute('UPDATE comments SET run_id=? WHERE id=?', (run_id, match['id']))


def _migrate_json_blobs(connection):
    """Move results(run, payload) and project_posts(payload) into the normalized tables.

    The old tables are kept as results_legacy and project_posts_legacy.
    """
    imported = set()
    if table_exists(connection, 'project_posts'):
        for project_id, key, payload in connection.execute(
                'SELECT project_id, post_key, payload FROM project_posts ORDER BY rowid').fetchall():
            post = json.loads(payload)
            post_id = _write_post(connection, None, project_id, None, post, key)
            for position, comment in enumerate(post.get('comments', [])):
                _insert_comment(connection, post_id, None, position, comment)
            imported.add(post_id)
        connection.execute('ALTER TABLE project_posts RENAME TO project_posts_legacy')
    if table_exists(connection, 'results'):
        project_of = dict(connection.execute('SELECT id, project_id FROM runs').fetchall())
        for run_id, payload in connection.execute('SELECT run, payload FROM results ORDER BY rowid').fetchall():
            row = json.loads(payload)
            project_id = project_of.get(run_id)
            post_id = _find_post(connection, project_id, run_id, post_key(row)) if project_id else None
            if post_id in imported:
                # Results of project runs hold only the comments that run added.
                connection.execute(
                    'UPDATE posts SET run_id=COALESCE(run_id, ?) WHERE id=?', (run_id, post_id))
                _link_result_comments(connection, run_id, post_id, row.get('comments', []))
                _record_run(connection, run_id, post_id, row.get('new_post', True), True, row)
            else:
                save_post(connection, run_id, project_id, row)
        connection.execute('ALTER TABLE results RENAME TO results_legacy')


def initialize_projects(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, config TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
    create_tables(connection)
    _assign_legacy_projects(connection)
    if connection.execute('PRAGMA user_version').fetchone()[0] < SCHEMA_VERSION:
        _migrate_json_blobs(connection)
        connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
