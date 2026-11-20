"""Offline tests for normalized post and comment storage."""
import json
import sqlite3
import unittest

from project_store import (
    completed_post_keys, delete_project_data, delete_run_data, initialize_projects, merge_post,
    post_key, project_posts, run_counts, run_posts, save_post,
)

PROJECT = 'a' * 32


def post(shortcode, comments=(), **fields):
    return {
        'post_url': f'https://www.instagram.com/p/{shortcode}/',
        'caption': 'caption', 'owner': 'brand', 'source': 'brand', 'source_type': 'profile',
        'scraped_at': '2026-11-01T00:00:00+00:00', 'total_likes': 10,
        'comments': list(comments), 'likers': [], **fields,
    }


def comment(username, text, **fields):
    return {'username': username, 'text': text, 'time': '2026-11-01T00:00:00+00:00', 'likes': 0, **fields}


def connect():
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE runs(id TEXT PRIMARY KEY, config TEXT,status TEXT,logs TEXT)')
    return connection


def add_run(connection, run_id, project_id=None):
    connection.execute(
        'INSERT INTO runs(id,config,status,logs,project_id) VALUES (?,?,?,?,?)',
        (run_id, '{}', 'completed', '', project_id),
    )


def without_none(value):
    if isinstance(value, dict):
        return {key: without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [without_none(item) for item in value]
    return value


def identity(item):
    return item.get('comment_id') or (item['username'].casefold(), item['text'].strip())


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.c = connect()
        initialize_projects(self.c)
        self.c.execute("INSERT INTO projects VALUES (?, '{}', 'now', 'now')", (PROJECT,))

    def test_project_runs_merge_posts_and_deduplicate_comments(self):
        add_run(self.c, 'r1', PROJECT)
        add_run(self.c, 'r2', PROJECT)
        first = post('ABC', [comment('Ali', 'hi'), comment('sara', 'nice', comment_id='9')])
        self.assertTrue(save_post(self.c, 'r1', PROJECT, first))
        second = post('ABC', [comment('ali', ' hi '), comment('sara', 'edited', comment_id='9', likes=4),
                              comment('reza', 'new')], total_likes=25, caption='')
        self.assertTrue(save_post(self.c, 'r2', PROJECT, second))
        self.assertFalse(save_post(self.c, 'r2', PROJECT, second))

        [merged] = project_posts(self.c, PROJECT)
        # A matched comment takes the newer values, as before.
        self.assertEqual([c['text'] for c in merged['comments']], [' hi ', 'edited', 'new'])
        self.assertEqual(merged['comments'][1]['likes'], 4)
        self.assertEqual(merged['caption'], 'caption')
        self.assertEqual(merged['total_likes'], 25)
        self.assertEqual(merged['first_collected_at'], first['scraped_at'])
        self.assertEqual(merged['shortcode'], 'ABC')

        [run1] = run_posts(self.c, 'r1')
        self.assertTrue(run1['new_post'])
        self.assertEqual(run1['total_likes'], 10)
        self.assertEqual([c['username'] for c in run1['comments']], ['ali', 'sara'])
        [run2] = run_posts(self.c, 'r2')
        self.assertFalse(run2['new_post'])
        self.assertEqual([c['text'] for c in run2['comments']], ['new'])
        self.assertEqual(run_counts(self.c), {
            'r1': {'posts_count': 1, 'comments_count': 2},
            'r2': {'posts_count': 0, 'comments_count': 1},
        })

    def test_unchanged_post_is_not_a_run_result_but_likes_are_recorded(self):
        add_run(self.c, 'r1', PROJECT)
        add_run(self.c, 'r2', PROJECT)
        save_post(self.c, 'r1', PROJECT, post('ABC', [comment('a', 'x')]))
        self.assertFalse(save_post(self.c, 'r2', PROJECT, post('ABC', [comment('a', 'x')], total_likes=99)))
        self.assertEqual(run_posts(self.c, 'r2'), [])
        self.assertEqual(self.c.execute(
            "SELECT total_likes FROM run_posts WHERE run_id='r2'").fetchone(), (99,))

    def test_reel_and_post_urls_share_a_key(self):
        add_run(self.c, 'r1', PROJECT)
        save_post(self.c, 'r1', PROJECT, post('ABC'))
        save_post(self.c, 'r1', PROJECT, {**post('ABC'), 'post_url': 'https://www.instagram.com/reel/ABC/'})
        self.assertEqual(len(project_posts(self.c, PROJECT)), 1)

    def test_standalone_runs_are_kept_apart(self):
        add_run(self.c, 's1')
        add_run(self.c, 's2')
        save_post(self.c, 's1', None, post('ABC', [comment('a', 'x')]))
        save_post(self.c, 's2', None, post('ABC', [comment('a', 'x')]))
        self.assertEqual(len(run_posts(self.c, 's1')[0]['comments']), 1)
        self.assertEqual(len(run_posts(self.c, 's2')[0]['comments']), 1)
        self.assertEqual(project_posts(self.c, PROJECT), [])

    def test_extra_fields_round_trip(self):
        add_run(self.c, 'r1', PROJECT)
        save_post(self.c, 'r1', PROJECT, post('ABC', [comment('a', 'x', reply_to='1')], comments_count=1,
                                              likers=['u1', 'u1', 'u2']))
        [stored] = project_posts(self.c, PROJECT)
        self.assertEqual(stored['comments_count'], 1)
        self.assertEqual(stored['likers'], ['u1', 'u2'])
        self.assertEqual(stored['comments'][0]['reply_to'], '1')
        self.assertNotIn('new_post', stored)

    def test_completed_post_keys(self):
        add_run(self.c, 'r1', PROJECT)
        save_post(self.c, 'r1', PROJECT, post('HAS', [comment('a', 'x')]))
        save_post(self.c, 'r1', PROJECT, post('NONE', reported_comment_count=0))
        save_post(self.c, 'r1', PROJECT, post('TODO'))
        self.assertEqual(completed_post_keys(self.c, PROJECT), {'HAS', 'NONE'})

    def test_deleting_a_run_keeps_project_data(self):
        add_run(self.c, 'r1', PROJECT)
        add_run(self.c, 's1')
        save_post(self.c, 'r1', PROJECT, post('ABC', [comment('a', 'x')]))
        save_post(self.c, 's1', None, post('XYZ', [comment('a', 'x')]))
        delete_run_data(self.c, 'r1')
        delete_run_data(self.c, 's1')
        self.assertEqual(run_posts(self.c, 'r1'), [])
        self.assertEqual(len(project_posts(self.c, PROJECT)[0]['comments']), 1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM posts WHERE project_id IS NULL').fetchone(), (0,))
        delete_project_data(self.c, PROJECT)
        for table in ('posts', 'comments', 'run_posts'):
            self.assertEqual(self.c.execute(f'SELECT COUNT(*) FROM {table}').fetchone(), (0,), table)


def legacy_store(connection, project_id, row):
    """The JSON-blob store_post from before normalization."""
    key = post_key(row)
    if not key:
        return None
    old = connection.execute(
        'SELECT payload FROM project_posts WHERE project_id=? AND post_key=?', (project_id, key)).fetchone()
    merged, added = merge_post(json.loads(old[0]) if old else {}, row)
    connection.execute(
        '''INSERT INTO project_posts VALUES (?,?,?)
           ON CONFLICT(project_id,post_key) DO UPDATE SET payload=excluded.payload''',
        (project_id, key, json.dumps(merged, ensure_ascii=False)))
    return {**row, 'shortcode': key, 'comments': added, 'new_post': not bool(old)} if not old or added else None


class MigrationTests(unittest.TestCase):
    def legacy_database(self):
        c = connect()
        c.execute('ALTER TABLE runs ADD COLUMN project_id TEXT')
        c.execute('ALTER TABLE runs ADD COLUMN started_at TEXT')
        c.execute('CREATE TABLE results(run TEXT,payload TEXT)')
        c.execute('CREATE TABLE projects(id TEXT PRIMARY KEY, config TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
        c.execute('CREATE TABLE project_posts(project_id TEXT, post_key TEXT, payload TEXT, PRIMARY KEY(project_id,post_key))')
        c.execute("INSERT INTO projects VALUES (?, '{}', 'now', 'now')", (PROJECT,))
        batches = {
            'r1': [post('A', [comment('a', 'one'), comment('b', 'two')]), post('B', reported_comment_count=0)],
            'r2': [post('A', [comment('A', 'one'), comment('c', 'three', comment_id='7')], total_likes=30),
                   post('B'), post('C', [comment('d', 'four')])],
            'r3': [post('C', [comment('d', 'four'), comment('d', 'four', time='2026-11-02T00:00:00+00:00')])],
        }
        for run_id, rows in batches.items():
            add_run(c, run_id, PROJECT)
            for row in rows:
                result = legacy_store(c, PROJECT, row)
                if result:
                    c.execute('INSERT INTO results VALUES (?,?)', (run_id, json.dumps(result)))
        add_run(c, 's1')
        for row in (post('Z', [comment('z', 'solo')]), {'post_url': 'https://www.instagram.com/p/DEMO/',
                                                         'total_likes': '12', 'comments': [{'username': 'demo', 'text': 'x'}],
                                                         'likers': ['demo']}):
            c.execute('INSERT INTO results VALUES (?,?)', ('s1', json.dumps(row)))
        return c

    def legacy_views(self, c):
        project = [json.loads(p) for p, in c.execute(
            'SELECT payload FROM project_posts WHERE project_id=? ORDER BY rowid DESC', (PROJECT,))]
        runs = {}
        for run_id, in c.execute('SELECT id FROM runs'):
            runs[run_id] = [json.loads(p) for p, in c.execute('SELECT payload FROM results WHERE run=?', (run_id,))]
        return project, runs

    def test_migration_preserves_project_and_run_views(self):
        c = self.legacy_database()
        legacy_project, legacy_runs = self.legacy_views(c)
        initialize_projects(c)

        self.assertEqual(without_none(project_posts(c, PROJECT)), without_none(legacy_project))
        for run_id, legacy in legacy_runs.items():
            new = run_posts(c, run_id)
            self.assertEqual(len(new), len(legacy), run_id)
            for old_row, new_row in zip(legacy, new):
                self.assertEqual(post_key(new_row), post_key(old_row))
                # Run views show each comment's latest merged values, so compare identities.
                self.assertEqual([identity(x) for x in new_row['comments']],
                                 [identity(x) for x in old_row['comments']], run_id)
                self.assertEqual(new_row['new_post'], old_row.get('new_post', True))
                self.assertEqual(str(new_row.get('total_likes')), str(old_row.get('total_likes')))
        counts = run_counts(c)
        for run_id, legacy in legacy_runs.items():
            self.assertEqual(counts[run_id]['posts_count'], sum(r.get('new_post', True) for r in legacy))
            self.assertEqual(counts[run_id]['comments_count'], sum(len(r['comments']) for r in legacy))

        tables = {name for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'results_legacy', 'project_posts_legacy'} <= tables)
        self.assertFalse({'results', 'project_posts'} & tables)
        self.assertEqual(c.execute('PRAGMA user_version').fetchone(), (1,))

        delete_run_data(c, 's1')
        self.assertEqual(c.execute("SELECT COUNT(*) FROM results_legacy WHERE run='s1'").fetchone(), (0,))

        before = c.execute('SELECT COUNT(*) FROM comments').fetchone()
        initialize_projects(c)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM comments').fetchone(), before)
        delete_project_data(c, PROJECT)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM project_posts_legacy').fetchone(), (0,))

    def test_runs_from_before_projects_are_grouped_and_merged(self):
        c = connect()
        c.execute('CREATE TABLE results(run TEXT,payload TEXT)')
        for run_id in ('old1', 'old2'):
            c.execute('INSERT INTO runs VALUES (?,?,?,?)',
                      (run_id, json.dumps({'title': 'Brand', 'profiles': ['brand'], 'login_password': 'x'}), 'completed', ''))
        c.execute('INSERT INTO results VALUES (?,?)', ('old1', json.dumps(post('A', [comment('a', 'one')]))))
        c.execute('INSERT INTO results VALUES (?,?)', ('old2', json.dumps(post('A', [comment('a', 'one'), comment('b', 'two')]))))
        initialize_projects(c)

        [(project_id, config)] = c.execute('SELECT id, config FROM projects').fetchall()
        self.assertNotIn('login_password', json.loads(config))
        [merged] = project_posts(c, project_id)
        self.assertEqual([x['text'] for x in merged['comments']], ['one', 'two'])
        self.assertEqual([x['text'] for x in run_posts(c, 'old2')[0]['comments']], ['two'])
        self.assertFalse(run_posts(c, 'old2')[0]['new_post'])

    def test_migration_inside_a_transaction(self):
        c = self.legacy_database()
        c.commit()
        c.execute('BEGIN IMMEDIATE')
        initialize_projects(c)
        self.assertTrue(c.in_transaction)
        c.rollback()
        self.assertEqual(c.execute('PRAGMA user_version').fetchone(), (0,))


if __name__ == '__main__':
    unittest.main()
