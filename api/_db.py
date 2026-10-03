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
COPY_FALLBACK_MAX = 50 * 1024 * 1024     # stream-copy ceiling when the Storage copy endpoint refuses cross-bucket


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


def _storage_headers(extra=None):
    h = {'apikey': SERVICE, 'Authorization': f'Bearer {SERVICE}'}
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


# ---------- storage ----------
def storage_sign_upload(bucket, path, upsert=False):
    """Signed upload URL (2 h) — the browser PUTs the bytes straight to Storage; Vercel never sees them.
    upsert=True lets the PUT replace an existing object (the token carries the flag — sample photo replacement)."""
    url = f'{SUPABASE_URL}/storage/v1/object/upload/sign/{bucket}/{urllib.parse.quote(path)}'
    extra = {'Content-Type': 'application/json'}
    if upsert:
        extra['x-upsert'] = 'true'
    status, _, raw = _transport.request('POST', url, _storage_headers(extra), b'{}')
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    if status != 200 or not body.get('url'):
        return None
    return {'signed_url': SUPABASE_URL + '/storage/v1' + body['url'], 'token': body.get('token')}


def storage_sign_download(bucket, path, expires=3600):
    """Signed read URL for a private object (the desk previews vault media with these)."""
    url = f'{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{urllib.parse.quote(path)}'
    status, _, raw = _transport.request('POST', url, _storage_headers({'Content-Type': 'application/json'}), json.dumps({'expiresIn': expires}).encode())
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    if status != 200 or not body.get('signedURL'):
        return None
    return SUPABASE_URL + '/storage/v1' + body['signedURL']


def storage_head(bucket, path):
    """→ (exists, bytes, mime) for an object in a bucket, via the service key."""
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}'
    status, headers, _ = _transport.request('HEAD', url, _storage_headers())
    if status != 200:
        return False, 0, ''
    h = {k.lower(): v for k, v in headers.items()}
    return True, int(h.get('content-length') or 0), h.get('content-type', '')


def storage_copy(src_bucket, src_path, dst_bucket, dst_path):
    """Copy an object across buckets server-side (publish: vault → public). Tries the Storage copy endpoint
    first; if the deployment predates cross-bucket copy, streams objects up to COPY_FALLBACK_MAX. → bool."""
    url = f'{SUPABASE_URL}/storage/v1/object/copy'
    body = json.dumps({'bucketId': src_bucket, 'sourceKey': src_path, 'destinationBucket': dst_bucket, 'destinationKey': dst_path}).encode()
    status, _, _ = _transport.request('POST', url, _storage_headers({'Content-Type': 'application/json'}), body, timeout=60)
    if status in (200, 201):
        return True
    exists, size, mime = storage_head(src_bucket, src_path)
    if not exists or size > COPY_FALLBACK_MAX:
        return False
    status, _, raw = _transport.request('GET', f'{SUPABASE_URL}/storage/v1/object/{src_bucket}/{urllib.parse.quote(src_path)}', _storage_headers(), timeout=60)
    if status != 200:
        return False
    status, _, _ = _transport.request('POST', f'{SUPABASE_URL}/storage/v1/object/{dst_bucket}/{urllib.parse.quote(dst_path)}',
                                       _storage_headers({'Content-Type': mime or 'application/octet-stream', 'x-upsert': 'true'}), raw, timeout=60)
    return status in (200, 201)


def storage_delete(bucket, paths):
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}'
    status, _, _ = _transport.request('DELETE', url, _storage_headers({'Content-Type': 'application/json'}), json.dumps({'prefixes': paths}).encode(), timeout=30)
    return status in (200, 201)


def public_url(bucket, path):
    return f'{SUPABASE_URL}/storage/v1/object/public/{bucket}/{urllib.parse.quote(path)}'


def public_base(bucket):
    return f'{SUPABASE_URL}/storage/v1/object/public/{bucket}/' if SUPABASE_URL else ''


def storage_get_json(bucket, path):
    """Read a small JSON object from a PUBLIC bucket (the sample-photo manifest). → dict or None."""
    if not SUPABASE_URL:
        return None
    status, _, raw = _transport.request('GET', public_url(bucket, path), {'Accept': 'application/json'}, timeout=8)
    if status != 200 or not raw:
        return None
    try:
        body = json.loads(raw)
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def storage_put_json(bucket, path, obj):
    """Write (upsert) a small JSON object with the service key. → bool."""
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{urllib.parse.quote(path)}'
    data = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    status, _, _ = _transport.request('POST', url, _storage_headers({'Content-Type': 'application/json', 'x-upsert': 'true', 'Cache-Control': 'max-age=60'}), data, timeout=30)
    return status in (200, 201)
