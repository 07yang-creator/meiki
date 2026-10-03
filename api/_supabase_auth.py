"""
_supabase_auth.py — Supabase token verifier (copied from Rakusalab 2026-10-03 and trimmed: mei roles live in
mei.members, not in Rakusalab's profiles table).

(Leading underscore → Vercel does not turn this into a route; it's imported by handlers.)

  bearer(headers)      → the Bearer token string, or ''.
  verify_token(token)  → the Supabase auth user dict {id, email, ...} for a valid access token,
                         else None. Validates via GET /auth/v1/user on EVERY call (Supabase checks
                         signature + expiry) — no local decode, no bypass, no test token.
"""
import json
import os
import urllib.request

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
ANON = os.environ.get('SUPABASE_ANON_KEY', '')


def bearer(headers) -> str:
    auth = headers.get('Authorization') or headers.get('authorization') or ''
    return auth[7:].strip() if auth[:7].lower() == 'bearer ' else ''


def verify_token(token: str):
    if not token or not (SUPABASE_URL and ANON):
        return None
    req = urllib.request.Request(
        f'{SUPABASE_URL}/auth/v1/user',
        headers={'apikey': ANON, 'Authorization': f'Bearer {token}'},
        method='GET')
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            u = json.loads(r.read())
            return u if u and u.get('id') else None
    except Exception:
        return None
