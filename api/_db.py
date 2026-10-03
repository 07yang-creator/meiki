# -*- coding: utf-8 -*-
"""_db.py — the one Supabase client of the mei API: PostgREST over schema `mei` + Storage, service key, server only.

The browser never talks to PostgREST for mei tables (plan §4); every read and write passes through here with
the service role key and the schema profile headers. `set_transport()` lets tests replace the HTTP layer with a
fake, so the handlers are exercised end to end without a network.

Supabase setting required once: Project → API → "Exposed schemas" must include `mei` (PostgREST refuses the
Accept-Profile otherwise). Recorded in README.md.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SERVICE = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
SCHEMA = 'mei'


class UrllibTransport:
    def request(self, method, url, headers, body=None, timeout=15):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()


_transport = UrllibTransport()


def set_transport(t):
    global _transport
    _transport = t


def configured():
    return bool(SUPABASE_URL and SERVICE)


def _headers(extra=None, content=True):
    h = {'apikey': SERVICE, 'Authorization': f'Bearer {SERVICE}', 'Accept-Profile': SCHEMA, 'Accept': 'application/json'}
    if content:
        h['Content-Profile'] = SCHEMA
        h['Content-Type'] = 'application/json'
    if extra:
        h.update(extra)
    return h


def rest(method, table, params=None, body=None, prefer=None):
    """→ (status, parsed json or None). params: dict of PostgREST query params (e.g. {'id': 'eq.<uuid>', 'select': '*'})."""
    url = f'{SUPABASE_URL}/rest/v1/{table}'
    if params:
        url += '?' + urllib.parse.urlencode(params, safe=',.*()')
    extra = {'Prefer': prefer} if prefer else None
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    status, _, raw = _transport.request(method, url, _headers(extra, content=body is not None), data)
    try:
        return status, (json.loads(raw) if raw else None)
    except ValueError:
        return status, None


def select(table, **params):
    params.setdefault('select', '*')
    status, rows = rest('GET', table, params)
    return rows if status == 200 and isinstance(rows, list) else []


def insert(table, row):
    status, rows = rest('POST', table, body=row, prefer='return=representation')
    return status, (rows[0] if isinstance(rows, list) and rows else rows)


def update(table, params, patch):
    status, rows = rest('PATCH', table, params, body=patch, prefer='return=representation')
    return status, (rows[0] if isinstance(rows, list) and rows else rows)


def storage_sign_upload(bucket, path):
    """Signed upload URL (2 h) — the browser PUTs the bytes straight to Storage; Vercel never sees them."""
    url = f'{SUPABASE_URL}/storage/v1/object/upload/sign/{bucket}/{urllib.parse.quote(path)}'
    status, _, raw = _transport.request('POST', url, {'apikey': SERVICE, 'Authorization': f'Bearer {SERVICE}', 'Content-Type': 'application/json'}, b'{}')
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    if status != 200 or not body.get('url'):
        return None
    return {'signed_url': SUPABASE_URL + '/storage/v1' + body['url'], 'token': body.get('token')}


def storage_head(bucket, path):
    """→ (exists, bytes, mime) for an object in a bucket, via the service key."""
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}'
    status, headers, _ = _transport.request('HEAD', url, {'apikey': SERVICE, 'Authorization': f'Bearer {SERVICE}'})
    if status != 200:
        return False, 0, ''
    h = {k.lower(): v for k, v in headers.items()}
    return True, int(h.get('content-length') or 0), h.get('content-type', '')
