"""Read post and comment fields from responses the Instagram page receives."""

import base64
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error

from direct_scraper import CollectionError


def timestamp(value):
    if isinstance(value, (int, float)) and 0 <= value < 253402300799:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return None


def edges(node, key):
    connection = node.get(key)
    if not isinstance(connection, dict):
        return []
    return [edge['node'] for edge in (connection.get('edges') or [])
            if isinstance(edge, dict) and isinstance(edge.get('node'), dict)]


class PostResponses:
    def __init__(self, shortcode, comment_limit):
        self.shortcode = shortcode
        self.comment_limit = comment_limit
        self.media_ids = set()
        if re.fullmatch(r'[A-Za-z0-9_-]{1,11}', shortcode):
            self.media_ids.add(str(int.from_bytes(base64.urlsafe_b64decode(shortcode.rjust(12, 'A')), 'big')))
        self.fields = {}
        self.comments = {}
        self.comment_payloads = []
        self.blocked = False
        self.json_responses = 0
        self.comment_responses = 0

    def receive(self, response):
        url = urlsplit(response.url)
        if url.hostname not in ('www.instagram.com', 'i.instagram.com'):
            return
        if response.request.resource_type not in ('fetch', 'xhr'):
            return
        if not (url.path.startswith('/api/') or url.path.rstrip('/') == '/graphql/query'):
            return
        if response.status in (401, 403, 429):
            self.blocked = True
            return
        if response.status >= 500 or 'json' not in response.headers.get('content-type', ''):
            return
        try:
            raw = response.text().removeprefix('for (;;);')
        except Error:
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            # GraphQL may deliver multiple JSON objects separated by newlines.
            for line in raw.splitlines():
                try:
                    self.read_payload(json.loads(line), response, url)
                except ValueError:
                    continue
            return
        self.read_payload(payload, response, url)

    def read_payload(self, payload, response, url):
        if not isinstance(payload, dict):
            return
        message = payload.get('message')
        if message in ('feedback_required', 'checkpoint_required', 'challenge_required', 'login_required'):
            self.blocked = True
            return
        if response.status >= 400:
            return
        self.json_responses += 1
        for key in ('items', 'media'):
            value = payload.get(key)
            if isinstance(value, dict):
                self.read_post(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self.read_post(item)
        data = payload.get('data')
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    self.read_post(value)
                    if 'comment' in key and self.request_matches_post(response.request, url):
                        self.read_comment_connection(value)
        match = re.fullmatch(
            r'/api/v1/media/([0-9]+)/comments(?:/[0-9]+/(?:inline_child_comments|child_comments))?/?',
            url.path,
        )
        if match:
            for key in ('comments', 'child_comments'):
                items = payload.get(key)
                if isinstance(items, list) and len(self.comment_payloads) < 30:
                    self.comment_payloads.append((match[1], items[:self.comment_limit]))

    def request_matches_post(self, request, url):
        form = parse_qs(request.post_data or url.query)
        try:
            variables = json.loads(form.get('variables', ['{}'])[0])
        except ValueError:
            return False
        if not isinstance(variables, dict):
            return False
        for values in (variables, variables.get('data'), variables.get('input')):
            if not isinstance(values, dict):
                continue
            if values.get('shortcode') == self.shortcode:
                return True
            if any(str(values.get(key, '')).split('_')[0] in self.media_ids
                   for key in ('media_id', 'mediaId', 'media_pk')):
                return True
            if any(str(values.get(key, '')) in self.comments
                   for key in ('comment_id', 'commentId', 'parent_comment_id')):
                return True
        return False

    def read_comment_connection(self, node):
        self.comment_responses += 1
        self.read_comments(edges(node, 'parent_comment_connection'))
        self.read_comments(edges(node, 'edge_media_to_parent_comment'))
        self.read_comments(edges(node, 'child_comment_connection'))
        self.read_comments(edges(node, 'edge_threaded_comments'))
        self.read_comments(edges({'connection': node}, 'connection'))
        for key in ('comments', 'child_comments'):
            if isinstance(node.get(key), list):
                self.read_comments(node[key])

    def read_post(self, node):
        if (node.get('shortcode') or node.get('code')) != self.shortcode:
            return
        media_id = str(node.get('pk') or node.get('id') or '').split('_')[0]
        if media_id.isdecimal():
            self.media_ids.add(media_id)
            self.fields['media_id'] = media_id
        owner = node.get('owner') or node.get('user')
        if isinstance(owner, dict) and isinstance(owner.get('username'), str):
            self.fields['owner'] = owner['username']
        caption = node.get('caption')
        caption_edges = edges(node, 'edge_media_to_caption')
        if caption_edges:
            caption = caption_edges[0]
        if isinstance(caption, dict) and isinstance(caption.get('text'), str):
            self.fields['caption'] = caption['text']
        published = timestamp(node.get('taken_at_timestamp') or node.get('taken_at'))
        if published:
            self.fields['published_at'] = published
        likes = node.get('like_count')
        if type(likes) is not int or likes < 0:
            for key in ('edge_media_preview_like', 'edge_liked_by'):
                connection = node.get(key)
                if isinstance(connection, dict) and type(connection.get('count')) is int:
                    likes = connection['count']
                    if likes >= 0:
                        break
        if type(likes) is int and likes >= 0:
            self.fields['total_likes'] = likes
        count = node.get('comment_count')
        if type(count) is int and count >= 0:
            self.fields['reported_comment_count'] = count
        for key in ('edge_media_to_parent_comment', 'edge_media_to_comment'):
            self.read_comments(edges(node, key))
        if isinstance(node.get('comments'), list):
            self.read_comments(node['comments'])

    def read_comments(self, items):
        for item in items:
            if len(self.comments) >= self.comment_limit:
                return
            if not isinstance(item, dict):
                continue
            text = item.get('text')
            owner = item.get('user') or item.get('owner')
            username = owner.get('username') if isinstance(owner, dict) else None
            if not isinstance(text, str) or not isinstance(username, str):
                continue
            created = timestamp(item.get('created_at'))
            key = str(item.get('pk') or item.get('id') or (username, text, created))
            likes = item.get('comment_like_count', item.get('like_count'))
            self.comments.setdefault(key, {
                'text': text, 'username': username, 'time': created,
                'likes': likes if isinstance(likes, int) else None,
            })
            for connection in ('edge_threaded_comments', 'child_comment_connection'):
                self.read_comments(edges(item, connection))
            for child_key in ('child_comments', 'preview_child_comments'):
                children = item.get(child_key)
                if isinstance(children, list):
                    self.read_comments(children)

    def read_pending_comments(self):
        unmatched = []
        for media_id, items in self.comment_payloads:
            if media_id in self.media_ids:
                self.comment_responses += 1
                self.read_comments(items)
            else:
                unmatched.append((media_id, items))
        self.comment_payloads = unmatched

    def check_access(self):
        if self.blocked:
            raise CollectionError('اینستاگرام دسترسی را محدود کرد یا تأیید خواست. اجرا متوقف شد.')
