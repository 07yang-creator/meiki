# -*- coding: utf-8 -*-
"""api/mei.py — 名木 Mei data function (slice P1 skeleton).

Public reads today come from data/*.json (the static preview). The next slice points `_load()` at the
`mei` schema in Supabase (service key, server-side, scoped by status) without changing the handlers or
the page. Every action is on an explicit allowlist; anything else is 404. Writes (intake, desk, inquiry,
briefs) arrive in P2–P6 and re-validate a Supabase JWT on every call (the Rakusalab rule, CLAUDE.md §3).
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')

PUBLIC_GET = ('health', 'client_config', 'trees', 'species', 'tree')
PUBLIC_STATUSES = ('published', 'reserved', 'sold')


def _load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)


def _public_tree(t):
    """Strip anything that must never leave the server (plan §5): garden, plot, internal price/notes, staff logistics detail."""
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
            dest.pop('note_staff', None)          # staff research context, never buyer copy (plan §7)
    return rows


def handle(action, qs):
    if action == 'health':
        return 200, {'ok': True, 'service': 'mei', 'source': 'seed'}
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


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body, cache='public, max-age=300'):
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', cache if status == 200 else 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        action = (qs.get('action') or [''])[0]
        if action not in PUBLIC_GET:
            return self._send(404, {'error': 'unknown action'})
        try:
            status, body = handle(action, qs)
        except Exception as e:  # never leak a traceback
            status, body = 500, {'error': type(e).__name__}
        self._send(status, body)

    def do_POST(self):
        self._send(405, {'error': 'writes arrive in P2+ (JWT-gated)'})
