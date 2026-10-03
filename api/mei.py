# -*- coding: utf-8 -*-
"""api/mei.py — 名木 Mei data function.

Public reads (gallery) still come from data/*.json until the desk publishes real trees (P3). Member actions
(P2: the supplier's 入 page) write to the `mei` schema through api/_db.py with the service key.

Every member action re-validates the Supabase JWT against /auth/v1/user on EVERY call (the Rakusalab rule), then
reads mei.members for the role. Client-side checks are cosmetic. Unknown actions are 404. Errors never carry a
traceback. Media bytes never pass through here: media_sign mints a signed upload URL, the browser PUTs to Storage,
media_commit records what landed after a HEAD.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import _db
import _supabase_auth

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')
VERIFY = _supabase_auth.verify_token          # tests replace this

PUBLIC_GET = ('health', 'client_config', 'trees', 'species', 'tree')
MEMBER_GET = ('me', 'my_trees', 'tree_get', 'species_all')
MEMBER_POST = ('tree_save', 'tree_submit', 'media_sign', 'media_commit', 'species_propose')
PUBLIC_STATUSES = ('published', 'reserved', 'sold')
SEASONS = ('spring', 'summer', 'autumn', 'winter')
VAULT = 'mei-vault'
MEDIA_MIMES = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/heic': 'heic', 'video/mp4': 'mp4', 'video/quicktime': 'mov'}
MEDIA_MAX_BYTES = 500 * 1024 * 1024
INT_FIELDS = ('height_cm', 'width_cm', 'trunk_girth_cm', 'root_ball_cm', 'age_years_est', 'est_gross_weight_kg', 'root_ball_dia_cm', 'root_ball_depth_cm')
TEXT_FIELDS = ('cultivar_ja', 'given_name_ja', 'plot_ref', 'supplier_notes_ja', 'form_id', 'nemawashi_method', 'planned_dig_window', 'site_access')
SUPPLIER_EDITABLE_STATUSES = ('draft', 'review')


# ---------- seed (public gallery, P1) ----------
def _load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)


def _public_tree(t):
    out = {k: v for k, v in t.items() if k not in ('garden_id', 'plot_ref', 'internal_ask_jpy', 'internal_notes', 'supplier_notes_ja')}
    L = dict(out.get('logistics') or {})
    out['logistics'] = {k: L.get(k) for k in ('nemawashi', 'nemawashi_at', 'root_ball_est_cm', 'est_weight_kg', 'crane_access', 'earliest_ship')}
    return out


def public_trees():
    trees = _load('trees.json')['trees']
    return [_public_tree(t) for t in trees if t.get('status') in PUBLIC_STATUSES and (t.get('status') != 'sold' or t.get('show_when_sold', True))]


def public_species():
    rows = _load('species.json')['species']
    for s in rows:
        for dest in (s.get('trade') or {}).values():
            dest.pop('note_staff', None)
    return rows


def handle(action, qs):
    if action == 'health':
        return 200, {'ok': True, 'service': 'mei', 'source': 'seed', 'db': _db.configured()}
    if action == 'client_config':
        return 200, {'supabase_url': os.environ.get('SUPABASE_URL', ''), 'supabase_anon_key': os.environ.get('SUPABASE_ANON_KEY', '')}
    if action == 'trees':
        return 200, {'trees': public_trees()}
    if action == 'species':
        return 200, {'species': public_species()}
    if action == 'tree':
        slug = (qs.get('slug') or [''])[0]
        rows = [t for t in public_trees() if t.get('id') == slug]
        return (200, {'tree': rows[0]}) if rows else (404, {'error': 'not found'})
    return 404, {'error': 'unknown action'}


# ---------- members ----------
def _member(user):
    rows = _db.select('members', user_id=f"eq.{user['id']}", active='eq.true', select='user_id,role,garden_id,name')
    return rows[0] if rows else None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _event(kind, subject_id, actor, action, diff=None):
    _db.insert('events', {'subject_kind': kind, 'subject_id': str(subject_id), 'actor': actor, 'action': action, 'diff': diff or {}})


def _own(member, tree):
    """A supplier may touch only trees of their own garden; staff/admin any."""
    return member['role'] in ('admin', 'staff') or (tree and tree.get('garden_id') == member.get('garden_id'))


def _tree(tree_id):
    if not tree_id:
        return None
    rows = _db.select('trees', id=f'eq.{tree_id}', limit='1')
    return rows[0] if rows else None


def _mint_catalog_no():
    year = datetime.now(timezone.utc).year
    rows = _db.select('trees', select='catalog_no', catalog_no=f'like.MEI-{year}-*', order='catalog_no.desc', limit='1')
    seq = int(rows[0]['catalog_no'].rsplit('-', 1)[1]) + 1 if rows else 1
    return f'MEI-{year}-{seq:03d}'


def _clean_fields(body, member):
    """Whitelist + type the editable fields. Returns (patch, error)."""
    patch = {}
    for k in INT_FIELDS:
        if k in body:
            v = body[k]
            if v in (None, ''):
                patch[k] = None
                continue
            try:
                v = int(v)
            except (TypeError, ValueError):
                return None, f'{k} must be an integer'
            if v < 0 or v > 100000:
                return None, f'{k} out of range'
            patch[k] = v
    for k in TEXT_FIELDS:
        if k in body:
            v = body[k]
            if v is not None and not isinstance(v, str):
                return None, f'{k} must be text'
            patch[k] = (v or '').strip()[:4000] or None
    if 'species_id' in body:
        sid = str(body['species_id'] or '').strip()
        if not re.match(r'^[a-z0-9-]{1,80}$', sid) or not _db.select('species', id=f'eq.{sid}', select='id'):
            return None, 'unknown species'
        patch['species_id'] = sid
    if 'best_season_override' in body:
        v = body['best_season_override']
        if v not in SEASONS and v not in (None, ''):
            return None, 'bad season'
        patch['best_season_override'] = v or None
    if 'nemawashi_status' in body:
        v = body['nemawashi_status']
        if v not in ('not_started', 'in_progress', 'done', None, ''):
            return None, 'bad nemawashi_status'
        patch['nemawashi_status'] = v or None
    if 'nemawashi_dates' in body:
        ds = body['nemawashi_dates'] or []
        if not isinstance(ds, list) or any(not re.match(r'^\d{4}-\d{2}-\d{2}$', str(d)) for d in ds):
            return None, 'nemawashi_dates must be YYYY-MM-DD'
        patch['nemawashi_dates'] = ds
    return patch, None


def tree_save(user, member, body):
    tree_id = body.get('id')
    patch, err = _clean_fields(body, member)
    if err:
        return 400, {'error': err}
    if tree_id:
        tree = _tree(tree_id)
        if not tree:
            return 404, {'error': 'tree not found'}
        if not _own(member, tree):
            return 403, {'error': 'not your tree'}
        if member['role'] == 'supplier' and tree['status'] not in SUPPLIER_EDITABLE_STATUSES:
            return 409, {'error': f"a {tree['status']} tree is read-only for the supplier"}
        if member['role'] == 'supplier' and tree['status'] == 'review':
            patch['status'] = 'draft'          # editing after 提出 pulls it back to draft, honestly
        status, row = _db.update('trees', {'id': f'eq.{tree_id}'}, patch)
        if status not in (200, 201):
            return 502, {'error': 'db update failed'}
        _event('tree', tree_id, user['id'], 'save', {k: patch[k] for k in patch})
        return 200, {'tree': row}
    if not patch.get('species_id'):
        return 400, {'error': 'species_id required'}
    if member['role'] == 'supplier' and not member.get('garden_id'):
        return 403, {'error': 'supplier without a garden'}
    row = dict(patch)
    garden = member.get('garden_id') if member['role'] == 'supplier' else (body.get('garden_id') or member.get('garden_id'))
    row.update({'garden_id': garden, 'status': 'draft', 'created_by': user['id']})
    for attempt in range(2):                   # catalog_no is unique; a race simply retries once
        row['catalog_no'] = _mint_catalog_no()
        row['slug'] = row['catalog_no'].lower()
        status, created = _db.insert('trees', row)
        if status in (200, 201):
            _event('tree', created['id'], user['id'], 'create', {'catalog_no': row['catalog_no']})
            return 201, {'tree': created}
        if status != 409:
            break
    return 502, {'error': 'db insert failed'}


def tree_submit(user, member, body):
    tree = _tree(body.get('id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    if not _own(member, tree):
        return 403, {'error': 'not your tree'}
    if tree['status'] != 'draft':
        return 409, {'error': f"cannot submit a {tree['status']} tree"}
    missing = [k for k in ('species_id', 'height_cm', 'width_cm') if not tree.get(k)]
    photos = _db.select('tree_media', tree_id=f"eq.{tree['id']}", kind='eq.photo', select='id,shot_no')
    if not photos:
        missing.append('photo')
    if missing:
        return 422, {'error': 'incomplete', 'missing': missing}
    status, row = _db.update('trees', {'id': f"eq.{tree['id']}"}, {'status': 'review', 'submitted_at': _now()})
    if status not in (200, 201):
        return 502, {'error': 'db update failed'}
    _event('tree', tree['id'], user['id'], 'submit')
    return 200, {'tree': row}


def media_sign(user, member, body):
    tree = _tree(body.get('tree_id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    if not _own(member, tree):
        return 403, {'error': 'not your tree'}
    mime = str(body.get('mime') or '')
    ext = MEDIA_MIMES.get(mime)
    if not ext:
        return 400, {'error': f'unsupported mime {mime!r}'}
    try:
        size = int(body.get('bytes') or 0)
    except (TypeError, ValueError):
        return 400, {'error': 'bytes must be an integer'}
    if size <= 0 or size > MEDIA_MAX_BYTES:
        return 400, {'error': 'file too large (500 MB max) or empty'}
    path = f"vault/{tree['id']}/{uuid.uuid4().hex}.{ext}"
    signed = _db.storage_sign_upload(VAULT, path)
    if not signed:
        return 502, {'error': 'storage sign failed'}
    return 200, {'bucket': VAULT, 'path': path, 'signed_url': signed['signed_url'], 'token': signed['token'], 'expires_in': 7200}


def media_commit(user, member, body):
    tree = _tree(body.get('tree_id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    if not _own(member, tree):
        return 403, {'error': 'not your tree'}
    path = str(body.get('path') or '')
    if not path.startswith(f"vault/{tree['id']}/") or '..' in path:
        return 400, {'error': 'path outside the tree'}
    kind = body.get('kind')
    if kind not in ('photo', 'video'):
        return 400, {'error': 'kind must be photo or video'}
    exists, size, mime = _db.storage_head(VAULT, path)
    if not exists:
        return 409, {'error': 'object not found in storage — upload first'}
    if mime and mime not in MEDIA_MIMES:
        return 400, {'error': f'stored mime {mime!r} not allowed'}
    shot = body.get('shot_no')
    if shot not in (None, '') and not (isinstance(shot, int) and 1 <= shot <= 12):
        return 400, {'error': 'shot_no 1..12'}
    season = body.get('season')
    if season not in SEASONS and season not in (None, ''):
        return 400, {'error': 'bad season'}
    taken = body.get('taken_at')
    if taken and not re.match(r'^\d{4}-\d{2}-\d{2}$', str(taken)):
        return 400, {'error': 'taken_at YYYY-MM-DD'}
    row = {'tree_id': tree['id'], 'kind': kind, 'bucket': VAULT, 'path': path, 'mime': mime or body.get('mime'), 'bytes': size,
           'width': body.get('width'), 'height': body.get('height'), 'duration_s': body.get('duration_s'),
           'shot_no': shot or None, 'season': season or None, 'taken_at': taken or None,
           'caption_ja': (body.get('caption_ja') or '')[:200] or None,
           'exif_stripped': bool(body.get('exif_stripped')), 'uploaded_by': user['id']}
    status, created = _db.insert('tree_media', row)
    if status not in (200, 201):
        return 502, {'error': 'db insert failed'}
    if shot == 1 and kind == 'photo' and not tree.get('cover_media_id'):
        _db.update('trees', {'id': f"eq.{tree['id']}"}, {'cover_media_id': created['id']})
    _event('tree', tree['id'], user['id'], 'media', {'path': path, 'kind': kind, 'shot_no': shot})
    return 201, {'media': created}


def species_propose(user, member, body):
    ja = str(body.get('ja_kanji') or '').strip()[:40]
    reading = str(body.get('ja_reading') or '').strip()[:60]
    if not ja:
        return 400, {'error': 'ja_kanji required'}
    dup = _db.select('species', ja_kanji=f'eq.{ja}', select='id,status')
    if dup:
        return 200, {'species': dup[0], 'existing': True}
    sid = 'pending-' + uuid.uuid4().hex[:10]
    row = {'id': sid, 'latin': f'Pending ({ja})', 'ja_kanji': ja, 'ja_reading': reading or None, 'status': 'pending_zh', 'created_by': user['id']}
    status, created = _db.insert('species', row)
    if status not in (200, 201):
        return 502, {'error': 'db insert failed'}
    _event('species', sid, user['id'], 'propose', {'ja_kanji': ja})
    return 201, {'species': created, 'existing': False}


def my_trees(user, member, qs):
    params = {'select': 'id,catalog_no,slug,status,species_id,given_name_ja,height_cm,width_cm,trunk_girth_cm,root_ball_cm,age_years_est,form_id,best_season_override,nemawashi_status,updated_at,cover_media_id',
              'order': 'updated_at.desc', 'limit': '200'}
    if member['role'] == 'supplier':
        params['garden_id'] = f"eq.{member['garden_id']}"
    return 200, {'trees': _db.select('trees', **params)}


def tree_get(user, member, qs):
    tree = _tree((qs.get('id') or [''])[0])
    if not tree:
        return 404, {'error': 'tree not found'}
    if not _own(member, tree):
        return 403, {'error': 'not your tree'}
    media = _db.select('tree_media', tree_id=f"eq.{tree['id']}", order='shot_no.asc', select='id,kind,path,mime,bytes,width,height,duration_s,shot_no,season,taken_at,caption_ja')
    if member['role'] == 'supplier':
        for k in ('internal_ask_jpy', 'internal_notes'):
            tree.pop(k, None)
    return 200, {'tree': tree, 'media': media}


def species_all(user, member, qs):
    rows = _db.select('species', select='id,latin,ja_kanji,ja_reading,ja_variants,zh_hans,en,category,best_season,rank,status', order='rank.asc')
    if not rows:                                   # registry not seeded yet → the seed file keeps the pick-list alive
        rows = [{'id': s['id'], 'latin': s['latin'], 'ja_kanji': s['ja'], 'ja_reading': s['ja_reading'], 'zh_hans': s['zh'], 'en': s['en'],
                 'category': s['category'], 'best_season': s['best_season'], 'rank': s['rank'], 'status': 'approved'} for s in _load('species.json')['species']]
    return 200, {'species': rows}


def member_handle(method, action, user, member, qs, body):
    if method == 'GET':
        if action == 'me':
            return 200, {'user': {'id': user['id'], 'email': user.get('email')}, 'member': member}
        if action == 'my_trees':
            return my_trees(user, member, qs)
        if action == 'tree_get':
            return tree_get(user, member, qs)
        if action == 'species_all':
            return species_all(user, member, qs)
    else:
        if action == 'tree_save':
            return tree_save(user, member, body)
        if action == 'tree_submit':
            return tree_submit(user, member, body)
        if action == 'media_sign':
            return media_sign(user, member, body)
        if action == 'media_commit':
            return media_commit(user, member, body)
        if action == 'species_propose':
            return species_propose(user, member, body)
    return 404, {'error': 'unknown action'}


def dispatch(method, action, headers, qs, body):
    """Everything the HTTP handler does, minus I/O — tests call this directly."""
    if method == 'GET' and action in PUBLIC_GET:
        return handle(action, qs)
    if (method == 'GET' and action in MEMBER_GET) or (method == 'POST' and action in MEMBER_POST):
        user = VERIFY(_supabase_auth.bearer(headers))
        if not user:
            return 401, {'error': 'login required'}
        if not _db.configured():
            return 503, {'error': 'database not configured'}
        member = _member(user)
        if not member:
            return 403, {'error': 'not a member'}
        return member_handle(method, action, user, member, qs, body or {})
    return 404, {'error': 'unknown action'}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body, cache='public, max-age=300'):
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', cache if status == 200 else 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _run(self, method):
        qs = parse_qs(urlparse(self.path).query)
        action = (qs.get('action') or [''])[0]
        body = None
        if method == 'POST':
            try:
                n = int(self.headers.get('Content-Length') or 0)
                if n > 1_000_000:
                    return self._send(413, {'error': 'body too large — media never travels through this function'})
                body = json.loads(self.rfile.read(n) or b'{}')
            except ValueError:
                return self._send(400, {'error': 'invalid json'})
        try:
            status, out = dispatch(method, action, self.headers, qs, body)
        except Exception as e:                     # never leak a traceback
            status, out = 500, {'error': type(e).__name__}
        cache = 'public, max-age=300' if action in PUBLIC_GET else 'private, no-store'
        self._send(status, out, cache)

    def do_GET(self):
        self._run('GET')

    def do_POST(self):
        self._run('POST')
