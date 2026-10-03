# -*- coding: utf-8 -*-
"""api/mei.py — 名木 Mei data function.

Public reads (the gallery) merge the 20 SAMPLE trees in data/trees.json with the REAL trees the desk has published in
the `mei` schema; real trees carry `real: true` and the page shows them first. Member actions (P2 入 for the supplier,
P3 审 for staff/admin) write to `mei` through api/_db.py with the service key.

Every member action re-validates the Supabase JWT against /auth/v1/user on EVERY call (the Rakusalab rule), then
reads mei.members for the role. Client-side checks are cosmetic. Unknown actions are 404. Errors never carry a
traceback. Media bytes never pass through here: media_sign / sample_sign mint a signed upload URL, the browser PUTs
to Storage, media_commit / sample_commit record what landed after a HEAD; tree_publish copies vault → public
bucket server-side inside Storage.
"""
import json
import os
import re
import time
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
MEMBER_GET = ('me', 'my_trees', 'tree_get', 'species_all', 'media_urls', 'queue', 'publish_check', 'species_pending')
MEMBER_POST = ('tree_save', 'tree_submit', 'media_sign', 'media_commit', 'species_propose',
               'tree_text_save', 'tree_set', 'tree_sendback', 'tree_publish', 'species_approve', 'sample_sign', 'sample_commit')
PUBLIC_STATUSES = ('published', 'reserved', 'sold')
SEASONS = ('spring', 'summer', 'autumn', 'winter')
TIERS = ('signature', 'collection', 'stock')
CATEGORIES = ('pine', 'conifer', 'maple', 'flowering', 'evergreen', 'deciduous', 'other')
STAFF = ('admin', 'staff')
VAULT = 'mei-vault'
PUBLIC_BUCKET = 'mei-public'
SAMPLE_MANIFEST = 'samples/manifest.json'
MEDIA_MIMES = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/heic': 'heic', 'video/mp4': 'mp4', 'video/quicktime': 'mov'}
PUBLIC_MIMES = ('image/jpeg', 'image/png', 'image/webp', 'video/mp4')     # what the mei-public bucket accepts
MEDIA_MAX_BYTES = 500 * 1024 * 1024
SAMPLE_MAX_BYTES = 20 * 1024 * 1024
INT_FIELDS = ('height_cm', 'width_cm', 'trunk_girth_cm', 'root_ball_cm', 'age_years_est', 'est_gross_weight_kg', 'root_ball_dia_cm', 'root_ball_depth_cm')
TEXT_FIELDS = ('cultivar_ja', 'given_name_ja', 'plot_ref', 'supplier_notes_ja', 'form_id', 'nemawashi_method', 'planned_dig_window', 'site_access')
DESK_TEXT_FIELDS = ('given_name_zh', 'given_name_en', 'cultivar_zh', 'earliest_ship_window')
SUPPLIER_EDITABLE_STATUSES = ('draft', 'review')
FORMS = {'chokkan': ('直干', '直幹', 'Formal upright'), 'kyokkan': ('曲干（模样木）', '曲幹（模様木）', 'Informal upright'), 'shakan': ('斜干', '斜幹', 'Slanting'),
         'sokan': ('双干', '双幹', 'Twin trunk'), 'kabudachi': ('丛生多干', '株立ち', 'Multi-stem clump'), 'monkaburi': ('门冠型', '門かぶり', 'Gate canopy'),
         'shidare': ('垂枝', '枝垂れ', 'Weeping'), 'tamachirashi': ('玉散', '玉散らし', 'Cloud pruned'), 'danzukuri': ('层云', '段作り', 'Tiered'), 'shizen': ('自然树形', '自然樹形', 'Natural form')}


# ---------- seed ----------
def _load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)


def _seed_species():
    return _load('species.json')['species']


def _seed_trees():
    return _load('trees.json')['trees']


def _showable(t):
    return t.get('status') in PUBLIC_STATUSES and (t.get('status') != 'sold' or t.get('show_when_sold', True))


def _public_tree(t):
    out = {k: v for k, v in t.items() if k not in ('garden_id', 'plot_ref', 'internal_ask_jpy', 'internal_notes', 'supplier_notes_ja')}
    L = dict(out.get('logistics') or {})
    out['logistics'] = {k: L.get(k) for k in ('nemawashi', 'nemawashi_at', 'root_ball_est_cm', 'est_weight_kg', 'crane_access', 'earliest_ship')}
    return out


def _sample_manifest():
    """{sample_id: {'<shot>-<season>': {'p': path, 'v': epoch}}} — kept in the public bucket, written by sample_commit."""
    if not _db.configured():
        return {}
    try:
        return _db.storage_get_json(PUBLIC_BUCKET, SAMPLE_MANIFEST) or {}
    except Exception:
        return {}


def _sample_src(entry):
    return _db.public_url(PUBLIC_BUCKET, entry['p']) + '?v=' + str(entry.get('v') or 0)


def _sample_trees():
    manifest = _sample_manifest()
    out = []
    for t in _seed_trees():
        if not _showable(t):
            continue
        t = _public_tree(t)
        t['sample'] = True
        got = manifest.get(t['id']) or {}
        for p in t.get('photos') or []:
            e = got.get(f"{p.get('shot')}-{p.get('season')}")
            if e and e.get('p'):
                p['src'] = _sample_src(e)
        out.append(t)
    return out


# ---------- real trees (published from the desk) → the sample shape ----------
def _normalize_tree(t, media, texts, forms, species_season):
    photos, video = [], None
    season_default = t.get('best_season_override') or species_season.get(t.get('species_id')) or 'summer'
    for m in media:
        if not m.get('public_path'):
            continue
        src = _db.public_url(PUBLIC_BUCKET, m['public_path'])
        if m.get('kind') == 'photo':
            photos.append({'shot': m.get('shot_no') or 0, 'season': m.get('season') or season_default, 'taken_at': m.get('taken_at'),
                           'caption_zh': m.get('caption_zh'), 'src': src})
        elif m.get('kind') == 'video' and not video:
            video = {'duration_s': m.get('duration_s'), 'taken_at': m.get('taken_at'), 'src': src}
    photos.sort(key=lambda p: (p['shot'], p['season']))
    text = {}
    for lang in ('zh', 'ja', 'en'):
        row = next((x for x in texts if x.get('lang') == lang), None)       # texts arrive newest first
        if row and (row.get('headline') or row.get('body')):
            text[lang] = {'headline': row.get('headline') or '', 'body': row.get('body') or ''}
    f = forms.get(t.get('form_id')) or ('', '', '')
    dates = t.get('nemawashi_dates') or []
    return {
        'id': t['slug'], 'catalog_no': t['catalog_no'], 'tier': t.get('tier') or 'collection', 'status': t['status'], 'species': t['species_id'], 'real': True,
        'given_name': {'zh': t.get('given_name_zh') or '', 'ja': t.get('given_name_ja') or '', 'en': t.get('given_name_en') or ''},
        'cultivar': t.get('cultivar_zh') or t.get('cultivar_ja') or None,
        'measures': {k: t.get(k) for k in ('height_cm', 'width_cm', 'trunk_girth_cm', 'root_ball_cm', 'age_years_est')},
        'form': {'zh': f[0], 'ja': f[1], 'en': f[2]},
        'best_season': t.get('best_season_override'),
        'text': text, 'photos': photos, 'video': video,
        'logistics': {'nemawashi': t.get('nemawashi_status'), 'nemawashi_at': (str(dates[-1])[:7] if dates else None),
                      'root_ball_est_cm': t.get('root_ball_dia_cm'), 'est_weight_kg': t.get('est_gross_weight_kg'),
                      'crane_access': None, 'earliest_ship': t.get('earliest_ship_window')},
        'published_at': (t.get('published_at') or '')[:10], 'sold_at': None, 'show_when_sold': t.get('show_when_sold', True),
        'sort_weight': t.get('sort_weight') or 0,
    }


def _forms():
    rows = _db.select('forms', select='id,ja,zh,en')
    out = dict(FORMS)
    for r in rows:
        out[r['id']] = (r.get('zh') or '', r.get('ja') or '', r.get('en') or '')
    return out


def _db_public_trees():
    if not _db.configured():
        return []
    try:
        rows = _db.select('trees', status=f"in.({','.join(PUBLIC_STATUSES)})", order='published_at.desc', limit='500')
        rows = [t for t in rows if _showable(t)]
        if not rows:
            return []
        ids = ','.join(t['id'] for t in rows)
        media = _db.select('tree_media', tree_id=f'in.({ids})', select='tree_id,kind,public_path,shot_no,season,taken_at,caption_zh,duration_s')
        texts = _db.select('tree_texts', tree_id=f'in.({ids})', source='eq.human', kind='eq.label', order='created_at.desc', select='tree_id,lang,headline,body,created_at')
        forms = _forms()
        species_season = {s['id']: s['best_season'] for s in _seed_species()}
        for s in _db.select('species', select='id,best_season'):
            species_season.setdefault(s['id'], s.get('best_season'))
        out = []
        for t in rows:
            out.append(_normalize_tree(t, [m for m in media if m.get('tree_id') == t['id']], [x for x in texts if x.get('tree_id') == t['id']], forms, species_season))
        return out
    except Exception:
        return []


def public_trees():
    return _db_public_trees() + _sample_trees()


def _db_species_extra(seed_ids):
    """Species approved on the desk that the seed file does not know, in the seed shape."""
    if not _db.configured():
        return []
    try:
        rows = _db.select('species', status='eq.approved', order='rank.asc')
        trade = {r['species_id']: r for r in _db.select('species_trade', destination='eq.CN', select='species_id,status,verified_at')}
    except Exception:
        return []
    out = []
    for s in rows:
        if s['id'] in seed_ids or not s.get('zh_hans'):
            continue
        tr = trade.get(s['id']) or {}
        k = {key: s.get(f'know_{key}_zh') for key in ('intro', 'origin', 'character', 'culture', 'growth', 'care')}
        out.append({'id': s['id'], 'latin': s['latin'], 'latin_note': None, 'ja': s.get('ja_kanji') or '', 'ja_reading': s.get('ja_reading') or '', 'zh': s['zh_hans'], 'zht': s.get('zh_hant') or s['zh_hans'],
                    'en': s.get('en') or '', 'category': s.get('category') or 'other', 'false_friend': bool(s.get('false_friend')), 'kanji_note': None,
                    'best_season': s.get('best_season') or 'summer', 'rank': s.get('rank') or 99,
                    'trade': {'CN': {'status': tr.get('status') or 'unknown', 'verified_at': str(tr.get('verified_at') or '')[:7] or None}},
                    'knowledge': ({'zh': k} if any(k.values()) else {}),
                    'links': {key: s.get(f'link_{key}') for key in ('baike', 'wiki_ja', 'wiki_en') if s.get(f'link_{key}')}})
    return out


def public_species():
    rows = _seed_species()
    for s in rows:
        for dest in (s.get('trade') or {}).values():
            dest.pop('note_staff', None)
    return rows + _db_species_extra({s['id'] for s in rows})


def handle(action, qs):
    if action == 'health':
        return 200, {'ok': True, 'service': 'mei', 'source': 'seed+db' if _db.configured() else 'seed', 'db': _db.configured()}
    if action == 'client_config':
        return 200, {'supabase_url': os.environ.get('SUPABASE_URL', ''), 'supabase_anon_key': os.environ.get('SUPABASE_ANON_KEY', '')}
    if action == 'trees':
        return 200, {'trees': public_trees(), 'public_base': _db.public_base(PUBLIC_BUCKET) if _db.configured() else ''}
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


def _staff(member):
    return member['role'] in STAFF


def _own(member, tree):
    """A supplier may touch only trees of their own garden; staff/admin any."""
    return _staff(member) or (tree and tree.get('garden_id') == member.get('garden_id'))


def _tree(tree_id):
    if not tree_id or not re.match(r'^[0-9a-f-]{8,40}$', str(tree_id)):
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


def _last_note(tree_id, action):
    rows = _db.select('events', subject_kind='eq.tree', subject_id=f'eq.{tree_id}', action=f'eq.{action}', order='at.desc', limit='1', select='diff,at')
    return (rows[0].get('diff') or {}).get('note') if rows else None


def tree_get(user, member, qs):
    tree = _tree((qs.get('id') or [''])[0])
    if not tree:
        return 404, {'error': 'tree not found'}
    if not _own(member, tree):
        return 403, {'error': 'not your tree'}
    media = _db.select('tree_media', tree_id=f"eq.{tree['id']}", order='shot_no.asc', select='id,kind,path,mime,bytes,width,height,duration_s,shot_no,season,taken_at,caption_ja,public_path')
    if member['role'] == 'supplier':
        for k in ('internal_ask_jpy', 'internal_notes'):
            tree.pop(k, None)
    out = {'tree': tree, 'media': media}
    if tree['status'] == 'draft':
        note = _last_note(tree['id'], 'sendback')
        if note:
            out['sendback'] = note
    if _staff(member):
        out['texts'] = _db.select('tree_texts', tree_id=f"eq.{tree['id']}", source='eq.human', order='created_at.desc', select='id,lang,kind,headline,body,created_at')
        garden = _db.select('gardens', id=f"eq.{tree['garden_id']}", select='id,name_ja') if tree.get('garden_id') else []
        out['garden'] = garden[0] if garden else None
    return 200, out


def species_all(user, member, qs):
    rows = _db.select('species', select='id,latin,ja_kanji,ja_reading,ja_variants,zh_hans,en,category,best_season,rank,status', order='rank.asc')
    if not rows:                                   # registry not seeded yet → the seed file keeps the pick-list alive
        rows = [{'id': s['id'], 'latin': s['latin'], 'ja_kanji': s['ja'], 'ja_reading': s['ja_reading'], 'zh_hans': s['zh'], 'en': s['en'],
                 'category': s['category'], 'best_season': s['best_season'], 'rank': s['rank'], 'status': 'approved'} for s in _seed_species()]
    return 200, {'species': rows}


def media_urls(user, member, qs):
    """Viewable URLs for a tree's media: the public URL once published, a 1 h signed URL for the vault otherwise."""
    tree = _tree((qs.get('id') or [''])[0])
    if not tree:
        return 404, {'error': 'tree not found'}
    if not _own(member, tree):
        return 403, {'error': 'not your tree'}
    media = _db.select('tree_media', tree_id=f"eq.{tree['id']}", order='shot_no.asc', select='id,kind,bucket,path,public_path,mime,shot_no,season,taken_at,duration_s,caption_ja,caption_zh')
    for m in media:
        m['url'] = _db.public_url(PUBLIC_BUCKET, m['public_path']) if m.get('public_path') else _db.storage_sign_download(m.get('bucket') or VAULT, m['path'])
    return 200, {'media': media}


# ---------- desk (staff / admin) ----------
def queue(user, member, qs):
    if not _staff(member):
        return 403, {'error': 'desk is for staff'}
    want = (qs.get('status') or ['review'])[0]
    params = {'select': 'id,catalog_no,slug,status,tier,species_id,given_name_ja,given_name_zh,height_cm,width_cm,garden_id,updated_at,submitted_at,published_at',
              'order': 'updated_at.desc', 'limit': '200'}
    if want != 'all':
        if want not in ('draft', 'review', 'published', 'reserved', 'sold', 'withdrawn'):
            return 400, {'error': 'bad status'}
        params['status'] = f'eq.{want}'
    rows = _db.select('trees', **params)
    gardens = {g['id']: g.get('name_ja') for g in _db.select('gardens', select='id,name_ja')}
    species = {s['id']: s for s in _db.select('species', select='id,ja_kanji,zh_hans,status')}
    counts = {}
    for m in _db.select('tree_media', select='tree_id,kind'):
        c = counts.setdefault(m['tree_id'], {'photo': 0, 'video': 0})
        c[m['kind']] = c.get(m['kind'], 0) + 1
    totals = {}
    for t in _db.select('trees', select='status'):
        totals[t['status']] = totals.get(t['status'], 0) + 1
    for t in rows:
        sp = species.get(t['species_id']) or {}
        t['garden'] = gardens.get(t.get('garden_id'))
        t['species_ja'] = sp.get('ja_kanji') or t['species_id']
        t['species_zh'] = sp.get('zh_hans')
        t['species_status'] = sp.get('status')
        t['photos'] = counts.get(t['id'], {}).get('photo', 0)
        t['videos'] = counts.get(t['id'], {}).get('video', 0)
    return 200, {'trees': rows, 'totals': totals}


def _gate(tree):
    """The publish checklist (plan §5.1). → (items, ready)."""
    sp = (_db.select('species', id=f"eq.{tree['species_id']}", select='id,status,zh_hans,latin') or [None])[0] or {}
    seed = {s['id']: s for s in _seed_species()}.get(tree['species_id'])
    sp_ok = bool(sp.get('status') == 'approved' and sp.get('zh_hans') and not str(sp.get('latin') or '').startswith('Pending'))
    texts = _db.select('tree_texts', tree_id=f"eq.{tree['id']}", lang='eq.zh', source='eq.human', kind='eq.label', select='id,body', order='created_at.desc', limit='1')
    media = _db.select('tree_media', tree_id=f"eq.{tree['id']}", kind='eq.photo', select='id,shot_no,mime')
    trade = _db.select('species_trade', species_id=f"eq.{tree['species_id']}", destination='eq.CN', select='status')
    trade_status = (trade[0]['status'] if trade else None) or (seed and seed['trade']['CN']['status']) or 'unknown'
    items = [
        {'key': 'species', 'required': True, 'ok': sp_ok, 'zh': '树种已审定（中文名 · 学名）'},
        {'key': 'measures', 'required': True, 'ok': bool(tree.get('height_cm') and tree.get('width_cm')), 'zh': '树高 · 冠幅已填'},
        {'key': 'photo1', 'required': True, 'ok': any(m.get('shot_no') == 1 for m in media), 'zh': '①正面 照片'},
        {'key': 'text_zh', 'required': True, 'ok': bool(texts and (texts[0].get('body') or '').strip()), 'zh': '中文文案（人工定稿）'},
        {'key': 'trade', 'required': False, 'ok': trade_status != 'unknown', 'zh': '出口状态已核（' + trade_status + '）'},
        {'key': 'tier', 'required': False, 'ok': tree.get('tier') in TIERS, 'zh': '等级已定（' + str(tree.get('tier') or '—') + '）'},
        {'key': 'public_mimes', 'required': False, 'ok': all((m.get('mime') or 'image/jpeg') in PUBLIC_MIMES for m in media), 'zh': '照片格式可公开（JPEG/PNG/WebP）'},
    ]
    return items, all(i['ok'] for i in items if i['required'])


def publish_check(user, member, qs):
    if not _staff(member):
        return 403, {'error': 'desk is for staff'}
    tree = _tree((qs.get('id') or [''])[0])
    if not tree:
        return 404, {'error': 'tree not found'}
    items, ready = _gate(tree)
    return 200, {'items': items, 'ready': ready, 'status': tree['status']}


def tree_publish(user, member, body):
    if member['role'] != 'admin':
        return 403, {'error': 'publish is admin-only'}
    tree = _tree(body.get('id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    items, ready = _gate(tree)
    if not ready:
        return 422, {'error': 'publish gate not passed', 'items': items}
    media = _db.select('tree_media', tree_id=f"eq.{tree['id']}", select='id,kind,bucket,path,mime,public_path')
    copied, skipped = [], []
    for m in media:
        if m.get('public_path'):
            continue
        if (m.get('mime') or 'image/jpeg') not in PUBLIC_MIMES:
            skipped.append(m['id'])
            continue
        dst = f"{tree['catalog_no']}/{m['path'].rsplit('/', 1)[-1]}"
        if _db.storage_copy(m.get('bucket') or VAULT, m['path'], PUBLIC_BUCKET, dst):
            _db.update('tree_media', {'id': f"eq.{m['id']}"}, {'public_path': dst})
            copied.append(m['id'])
        else:
            skipped.append(m['id'])
    patch = {'status': 'published', 'published_by': user['id']}
    if not tree.get('published_at'):
        patch['published_at'] = _now()
    status, row = _db.update('trees', {'id': f"eq.{tree['id']}"}, patch)
    if status not in (200, 201):
        return 502, {'error': 'db update failed'}
    _event('tree', tree['id'], user['id'], 'publish', {'copied': len(copied), 'skipped': len(skipped)})
    return 200, {'tree': row, 'copied': copied, 'skipped': skipped}


def tree_sendback(user, member, body):
    if not _staff(member):
        return 403, {'error': 'desk is for staff'}
    tree = _tree(body.get('id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    if tree['status'] not in ('review', 'draft'):
        return 409, {'error': f"cannot send back a {tree['status']} tree"}
    note = str(body.get('note') or '').strip()[:1000]
    if not note:
        return 400, {'error': 'note required'}
    status, row = _db.update('trees', {'id': f"eq.{tree['id']}"}, {'status': 'draft'})
    if status not in (200, 201):
        return 502, {'error': 'db update failed'}
    _event('tree', tree['id'], user['id'], 'sendback', {'note': note})
    return 200, {'tree': row}


def tree_set(user, member, body):
    """Desk-side attributes: tier, Chinese/English names, sort weight, and the sold/reserved/withdrawn/re-listed states."""
    if not _staff(member):
        return 403, {'error': 'desk is for staff'}
    tree = _tree(body.get('id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    patch = {}
    if 'tier' in body:
        if body['tier'] not in TIERS:
            return 400, {'error': 'bad tier'}
        patch['tier'] = body['tier']
    for k in DESK_TEXT_FIELDS:
        if k in body:
            v = body[k]
            if v is not None and not isinstance(v, str):
                return 400, {'error': f'{k} must be text'}
            patch[k] = (v or '').strip()[:80] or None
    if 'sort_weight' in body:
        try:
            patch['sort_weight'] = max(-1000, min(1000, int(body['sort_weight'] or 0)))
        except (TypeError, ValueError):
            return 400, {'error': 'sort_weight must be an integer'}
    if 'show_when_sold' in body:
        patch['show_when_sold'] = bool(body['show_when_sold'])
    if 'best_season_override' in body:
        v = body['best_season_override']
        if v not in SEASONS and v not in (None, ''):
            return 400, {'error': 'bad season'}
        patch['best_season_override'] = v or None
    if 'status' in body:
        want = body['status']
        if want not in ('reserved', 'sold', 'withdrawn', 'published'):
            return 400, {'error': 'status must be reserved | sold | withdrawn | published (publishing a new tree is tree_publish)'}
        if want in ('withdrawn', 'published') and member['role'] != 'admin':
            return 403, {'error': f'{want} is admin-only'}
        if not tree.get('published_at'):
            return 409, {'error': 'the tree was never published — use tree_publish'}
        patch['status'] = want
    if not patch:
        return 400, {'error': 'nothing to set'}
    status, row = _db.update('trees', {'id': f"eq.{tree['id']}"}, patch)
    if status not in (200, 201):
        return 502, {'error': 'db update failed'}
    _event('tree', tree['id'], user['id'], 'set', patch)
    return 200, {'tree': row}


def tree_text_save(user, member, body):
    if not _staff(member):
        return 403, {'error': 'desk is for staff'}
    tree = _tree(body.get('id'))
    if not tree:
        return 404, {'error': 'tree not found'}
    lang = body.get('lang')
    if lang not in ('zh', 'ja', 'en'):
        return 400, {'error': 'lang zh | ja | en'}
    headline = str(body.get('headline') or '').strip()[:200]
    text = str(body.get('body') or '').strip()[:4000]
    if not headline and not text:
        return 400, {'error': 'headline or body required'}
    status, row = _db.insert('tree_texts', {'tree_id': tree['id'], 'lang': lang, 'kind': 'label', 'headline': headline or None, 'body': text or None, 'source': 'human', 'created_by': user['id']})
    if status not in (200, 201):
        return 502, {'error': 'db insert failed'}
    _event('tree', tree['id'], user['id'], 'text', {'lang': lang, 'chars': len(text)})
    return 201, {'text': row}


def species_pending(user, member, qs):
    if not _staff(member):
        return 403, {'error': 'desk is for staff'}
    rows = _db.select('species', status='eq.pending_zh', order='created_at.desc', select='id,latin,ja_kanji,ja_reading,zh_hans,en,category,best_season,rank,status,created_at')
    return 200, {'species': rows}


LATIN_RX = re.compile(r"^[A-Z][a-z]+( [a-z×'’.-]+| [A-Z][a-z]+| var\.| spp\.| f\.)*$")


def species_approve(user, member, body):
    if member['role'] != 'admin':
        return 403, {'error': 'registry approval is admin-only'}
    sid = str(body.get('id') or '')
    row = (_db.select('species', id=f'eq.{sid}', limit='1') or [None])[0] if re.match(r'^[a-z0-9-]{1,80}$', sid) else None
    if not row:
        return 404, {'error': 'species not found'}
    zh = str(body.get('zh_hans') or '').strip()[:60]
    latin = ' '.join(str(body.get('latin') or '').split())[:80]
    if not zh or not latin:
        return 400, {'error': 'zh_hans and latin required'}
    if not LATIN_RX.match(latin):
        return 400, {'error': 'latin must look like a binomial (Genus species / Genus spp.)'}
    patch = {'zh_hans': zh, 'latin': latin, 'status': 'approved', 'approved_by': user['id'], 'approved_at': _now()}
    for k in ('zh_hant', 'en', 'kanji_note'):
        if body.get(k):
            patch[k] = str(body[k]).strip()[:200]
    if body.get('category'):
        if body['category'] not in CATEGORIES:
            return 400, {'error': 'bad category'}
        patch['category'] = body['category']
    if body.get('best_season'):
        if body['best_season'] not in SEASONS:
            return 400, {'error': 'bad season'}
        patch['best_season'] = body['best_season']
    if body.get('rank') not in (None, ''):
        try:
            patch['rank'] = max(1, min(999, int(body['rank'])))
        except (TypeError, ValueError):
            return 400, {'error': 'rank must be an integer'}
    status, updated = _db.update('species', {'id': f'eq.{sid}'}, patch)
    if status == 409:
        return 409, {'error': 'that Latin name is already registered'}
    if status not in (200, 201):
        return 502, {'error': 'db update failed'}
    _event('species', sid, user['id'], 'approve', {'zh_hans': zh, 'latin': latin})
    return 200, {'species': updated}


# ---------- sample photos (temporary: staff fill the 20 samples with real shots) ----------
def _sample_target(body):
    sid = str(body.get('sample_id') or '')
    if not any(t['id'] == sid and t.get('sample') for t in _seed_trees()):
        return None, (404, {'error': 'unknown sample'})
    shot, season = body.get('shot'), body.get('season')
    if not (isinstance(shot, int) and 1 <= shot <= 10):
        return None, (400, {'error': 'shot 1..10'})
    if season not in SEASONS:
        return None, (400, {'error': 'bad season'})
    return f'samples/{sid}/{shot}-{season}.jpg', None


def sample_sign(user, member, body):
    if not _staff(member):
        return 403, {'error': 'staff only'}
    path, err = _sample_target(body)
    if err:
        return err
    if body.get('mime') != 'image/jpeg':
        return 400, {'error': 'samples are JPEG (the page re-encodes before upload)'}
    try:
        size = int(body.get('bytes') or 0)
    except (TypeError, ValueError):
        return 400, {'error': 'bytes must be an integer'}
    if size <= 0 or size > SAMPLE_MAX_BYTES:
        return 400, {'error': 'file too large (20 MB max) or empty'}
    signed = _db.storage_sign_upload(PUBLIC_BUCKET, path, upsert=True)
    if not signed:
        return 502, {'error': 'storage sign failed'}
    return 200, {'bucket': PUBLIC_BUCKET, 'path': path, 'signed_url': signed['signed_url'], 'token': signed['token'], 'expires_in': 7200}


def sample_commit(user, member, body):
    if not _staff(member):
        return 403, {'error': 'staff only'}
    path, err = _sample_target(body)
    if err:
        return err
    exists, size, mime = _db.storage_head(PUBLIC_BUCKET, path)
    if not exists:
        return 409, {'error': 'object not found in storage — upload first'}
    manifest = _sample_manifest()
    entry = {'p': path, 'v': int(time.time())}
    manifest.setdefault(body['sample_id'], {})[f"{body['shot']}-{body['season']}"] = entry
    if not _db.storage_put_json(PUBLIC_BUCKET, SAMPLE_MANIFEST, manifest):
        return 502, {'error': 'manifest write failed'}
    _event('tree', body['sample_id'], user['id'], 'sample_photo', {'path': path, 'bytes': size})
    return 200, {'src': _sample_src(entry), 'path': path}


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
        if action == 'media_urls':
            return media_urls(user, member, qs)
        if action == 'queue':
            return queue(user, member, qs)
        if action == 'publish_check':
            return publish_check(user, member, qs)
        if action == 'species_pending':
            return species_pending(user, member, qs)
    else:
        fn = {'tree_save': tree_save, 'tree_submit': tree_submit, 'media_sign': media_sign, 'media_commit': media_commit, 'species_propose': species_propose,
              'tree_text_save': tree_text_save, 'tree_set': tree_set, 'tree_sendback': tree_sendback, 'tree_publish': tree_publish,
              'species_approve': species_approve, 'sample_sign': sample_sign, 'sample_commit': sample_commit}.get(action)
        if fn:
            return fn(user, member, body)
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
