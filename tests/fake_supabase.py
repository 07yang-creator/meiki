"""A fake Supabase for the API tests: just enough PostgREST (eq · neq · like · in · order · limit) and Storage
(signed upload · signed download · HEAD · copy · public GET · upsert POST · DELETE) for the handlers' request shapes.
Installed with `_db.set_transport(FakeSupabase())`; nothing here touches a network."""
import json
import re
import uuid
from urllib.parse import parse_qsl, unquote, urlparse

TABLES = ('members', 'gardens', 'species', 'species_trade', 'forms', 'trees', 'tree_media', 'tree_texts', 'events')


class FakeSupabase:
    def __init__(self):
        self.tables = {t: [] for t in TABLES}
        self.objects = {}        # (bucket, path) → (bytes, mime)
        self.json_objects = {}   # (bucket, path) → dict (small JSON objects written with the service key)
        self.calls = []
        self.sign_headers = []   # headers seen on signed-upload creation (upsert flag)
        self._clock = 0

    # ---- PostgREST ----
    def _match(self, rows, params):
        out = rows
        for k, v in params.items():
            if k in ('select', 'order', 'limit'):
                continue
            op, _, val = v.partition('.')
            if op == 'eq':
                out = [r for r in out if str(r.get(k)) == val or (val == 'true' and r.get(k) is True) or (val == 'false' and r.get(k) is False)]
            elif op == 'neq':
                out = [r for r in out if str(r.get(k)) != val]
            elif op == 'like':
                rx = '^' + re.escape(val).replace('\\*', '.*') + '$'
                out = [r for r in out if re.match(rx, str(r.get(k) or ''))]
            elif op == 'in':
                wanted = set(val.strip('()').split(','))
                out = [r for r in out if str(r.get(k)) in wanted]
        if 'order' in params:
            col, _, d = params['order'].split(',')[0].partition('.')
            out = sorted(out, key=lambda r: str(r.get(col) or ''), reverse=(d == 'desc'))
        if 'limit' in params:
            out = out[:int(params['limit'])]
        return out

    def _tick(self):
        self._clock += 1
        return '2026-10-03T00:%02d:%02dZ' % (self._clock // 60, self._clock % 60)

    def request(self, method, url, headers, body=None, timeout=15):
        self.calls.append((method, url))
        u = urlparse(url)
        params = dict(parse_qsl(u.query))
        if u.path.startswith('/storage/v1/'):
            return self._storage(method, u, headers, body)
        table = u.path.rsplit('/', 1)[1]
        rows = self.tables[table]
        if method == 'GET':
            return 200, {}, json.dumps(self._match(rows, params)).encode()
        data = json.loads(body or b'{}')
        if method == 'POST':
            if table == 'trees' and any(r['catalog_no'] == data.get('catalog_no') for r in rows):
                return 409, {}, b'{"message":"duplicate"}'
            if table == 'species' and any(r.get('latin') == data.get('latin') or r.get('id') == data.get('id') for r in rows):
                return 409, {}, b'{"message":"duplicate"}'
            row = dict(data)
            row.setdefault('id', str(uuid.uuid4()))
            stamp = self._tick()
            row.setdefault('updated_at', stamp)
            row.setdefault('created_at', stamp)
            row.setdefault('at', stamp)
            rows.append(row)
            return 201, {}, json.dumps([row]).encode()
        if method == 'PATCH':
            hit = self._match(rows, params)
            if table == 'species' and 'latin' in data and any(r.get('latin') == data['latin'] and r not in hit for r in rows):
                return 409, {}, b'{"message":"duplicate latin"}'
            for r in hit:
                r.update(data)
                r['updated_at'] = self._tick()
            return 200, {}, json.dumps(hit).encode()
        return 500, {}, b''

    # ---- Storage ----
    def _storage(self, method, u, headers, body):
        p = u.path[len('/storage/v1/'):]
        if p.startswith('object/upload/sign/'):
            bucket, path = p[len('object/upload/sign/'):].split('/', 1)
            self.sign_headers.append(dict(headers))
            return 200, {}, json.dumps({'url': f'/object/upload/sign/{bucket}/{path}?token=signed', 'token': 'tok'}).encode()
        if p.startswith('object/sign/'):
            bucket, path = p[len('object/sign/'):].split('/', 1)
            if (bucket, unquote(path)) not in self.objects:
                return 400, {}, b'{"error":"not found"}'
            return 200, {}, json.dumps({'signedURL': f'/object/sign/{bucket}/{path}?token=read'}).encode()
        if p == 'object/copy':
            d = json.loads(body or b'{}')
            src = (d.get('bucketId'), d.get('sourceKey'))
            if src not in self.objects:
                return 400, {}, b'{"error":"source missing"}'
            self.objects[(d.get('destinationBucket'), d.get('destinationKey'))] = self.objects[src]
            return 200, {}, b'{"Key":"ok"}'
        if p.startswith('object/public/'):
            bucket, path = p[len('object/public/'):].split('/', 1)
            key = (bucket, unquote(path))
            if key in self.json_objects:
                return 200, {'Content-Type': 'application/json'}, json.dumps(self.json_objects[key]).encode()
            return (200, {'Content-Type': self.objects[key][1]}, b'x') if key in self.objects else (404, {}, b'{"error":"not found"}')
        if p.startswith('object/'):
            rest = p[len('object/'):]
            if method == 'DELETE':
                d = json.loads(body or b'{}')
                for path in d.get('prefixes') or []:
                    self.objects.pop((rest, path), None)
                return 200, {}, b'[]'
            bucket, path = rest.split('/', 1)
            key = (bucket, unquote(path))
            if method == 'HEAD':
                obj = self.objects.get(key)
                if not obj and key in self.json_objects:
                    return 200, {'Content-Length': '2', 'Content-Type': 'application/json'}, b''
                return (200, {'Content-Length': str(obj[0]), 'Content-Type': obj[1]}, b'') if obj else (404, {}, b'')
            if method == 'GET':
                obj = self.objects.get(key)
                return (200, {'Content-Type': obj[1]}, b'x' * min(obj[0], 64)) if obj else (404, {}, b'')
            if method == 'POST':
                mime = (headers or {}).get('Content-Type', 'application/octet-stream')
                if key in self.objects and (headers or {}).get('x-upsert') != 'true':
                    return 400, {}, b'{"error":"exists"}'
                if mime == 'application/json':
                    self.json_objects[key] = json.loads(body or b'{}')
                self.objects[key] = (len(body or b''), mime)
                return 200, {}, b'{"Key":"ok"}'
        return 404, {}, b''
