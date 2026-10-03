"""Intake API locks (P2): every member action needs a valid token AND a mei.members row; a supplier touches only
their garden's trees; media never passes through the function (sign → PUT elsewhere → commit after HEAD);
submit demands the minimum record; catalog numbers are minted server-side. Runs against a fake Supabase."""
import json
import os
import re
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'api'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _db                                    # noqa: E402
import mei as api                             # noqa: E402
from fake_supabase import FakeSupabase        # noqa: E402

GARDEN_A, GARDEN_B = str(uuid.uuid4()), str(uuid.uuid4())
SUP_A = {'id': str(uuid.uuid4()), 'email': 'a@garden.jp'}
SUP_B = {'id': str(uuid.uuid4()), 'email': 'b@garden.jp'}
STAFF = {'id': str(uuid.uuid4()), 'email': 'staff@mei'}
NOBODY = {'id': str(uuid.uuid4()), 'email': 'x@x'}
TOKENS = {'tok-a': SUP_A, 'tok-b': SUP_B, 'tok-staff': STAFF, 'tok-nobody': NOBODY}


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase()
    f.tables['members'] = [
        {'user_id': SUP_A['id'], 'role': 'supplier', 'garden_id': GARDEN_A, 'name': 'A', 'active': True},
        {'user_id': SUP_B['id'], 'role': 'supplier', 'garden_id': GARDEN_B, 'name': 'B', 'active': True},
        {'user_id': STAFF['id'], 'role': 'staff', 'garden_id': None, 'name': 'S', 'active': True},
    ]
    f.tables['species'] = [{'id': 'acer-palmatum', 'latin': 'Acer palmatum', 'ja_kanji': '紅葉', 'status': 'approved', 'rank': 5, 'best_season': 'autumn'}]
    _db.set_transport(f)
    monkeypatch.setattr(_db, 'SUPABASE_URL', 'https://fake.supabase.co')
    monkeypatch.setattr(_db, 'SERVICE', 'service-key')
    monkeypatch.setattr(api, 'VERIFY', lambda tok: TOKENS.get(tok))
    yield f
    _db.set_transport(_db.UrllibTransport())


def call(method, action, token=None, body=None, **qs):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    return api.dispatch(method, action, headers, {k: [v] for k, v in qs.items()}, body)


def test_public_reads_need_no_token(fake):
    assert call('GET', 'health')[0] == 200
    assert call('GET', 'trees')[0] == 200


def test_member_actions_require_token_and_membership(fake):
    assert call('GET', 'me')[0] == 401
    assert call('GET', 'me', 'bad-token')[0] == 401
    assert call('GET', 'me', 'tok-nobody')[0] == 403
    status, out = call('GET', 'me', 'tok-a')
    assert status == 200 and out['member']['role'] == 'supplier'
    assert call('POST', 'tree_save', None, {'species_id': 'acer-palmatum'})[0] == 401


def test_unknown_actions_are_404_even_with_a_token(fake):
    assert call('GET', 'drop_everything', 'tok-staff')[0] == 404
    assert call('POST', 'me', 'tok-staff', {})[0] == 404          # GET-only action via POST


def test_supplier_creates_a_draft_with_a_minted_catalog_no(fake):
    status, out = call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum', 'height_cm': '460', 'width_cm': 380, 'given_name_ja': '紅雨'})
    assert status == 201
    t = out['tree']
    assert re.match(r'^MEI-\d{4}-001$', t['catalog_no']) and t['status'] == 'draft' and t['garden_id'] == GARDEN_A
    assert t['height_cm'] == 460
    status, out2 = call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum'})
    assert out2['tree']['catalog_no'].endswith('-002')


def test_supplier_cannot_touch_another_garden_or_set_garden(fake):
    _, a = call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum'})
    tid = a['tree']['id']
    assert call('POST', 'tree_save', 'tok-b', {'id': tid, 'height_cm': 1})[0] == 403
    assert call('GET', 'tree_get', 'tok-b', id=tid)[0] == 403
    assert call('POST', 'media_sign', 'tok-b', {'tree_id': tid, 'mime': 'image/jpeg', 'bytes': 100})[0] == 403
    _, created = call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum', 'garden_id': GARDEN_B})
    assert created['tree']['garden_id'] == GARDEN_A, 'a supplier never chooses the garden'
    assert call('GET', 'tree_get', 'tok-staff', id=tid)[0] == 200, 'staff read any tree'


def test_field_validation(fake):
    assert call('POST', 'tree_save', 'tok-a', {'species_id': 'nope'})[0] == 400
    assert call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum', 'height_cm': 'tall'})[0] == 400
    assert call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum', 'best_season_override': 'monsoon'})[0] == 400
    assert call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum', 'nemawashi_dates': ['2026-3-1']})[0] == 400
    assert call('POST', 'tree_save', 'tok-a', {})[0] == 400


def test_media_sign_then_commit_never_moves_bytes_through_the_function(fake):
    _, a = call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum'})
    tid = a['tree']['id']
    assert call('POST', 'media_sign', 'tok-a', {'tree_id': tid, 'mime': 'image/gif', 'bytes': 100})[0] == 400
    assert call('POST', 'media_sign', 'tok-a', {'tree_id': tid, 'mime': 'video/mp4', 'bytes': 600 * 1024 * 1024})[0] == 400
    status, s = call('POST', 'media_sign', 'tok-a', {'tree_id': tid, 'mime': 'image/jpeg', 'bytes': 1234})
    assert status == 200 and s['path'].startswith(f'vault/{tid}/') and s['path'].endswith('.jpg') and s['signed_url'].startswith('https://fake.supabase.co/storage/v1/')
    # commit before the upload landed → 409
    assert call('POST', 'media_commit', 'tok-a', {'tree_id': tid, 'path': s['path'], 'kind': 'photo', 'shot_no': 1, 'season': 'autumn', 'taken_at': '2026-09-28'})[0] == 409
    fake.objects[('mei-vault', s['path'])] = (1234, 'image/jpeg')
    assert call('POST', 'media_commit', 'tok-a', {'tree_id': tid, 'path': 'vault/other/x.jpg', 'kind': 'photo'})[0] == 400
    status, c = call('POST', 'media_commit', 'tok-a', {'tree_id': tid, 'path': s['path'], 'kind': 'photo', 'shot_no': 1, 'season': 'autumn', 'taken_at': '2026-09-28', 'exif_stripped': True})
    assert status == 201 and c['media']['bytes'] == 1234 and c['media']['shot_no'] == 1
    tree = [t for t in fake.tables['trees'] if t['id'] == tid][0]
    assert tree['cover_media_id'] == c['media']['id'], 'the first ①正面 becomes the cover'
    assert not any('/storage/v1/object/mei-vault' in u and m in ('POST', 'PUT') for m, u in fake.calls), 'no bytes through the function'


def test_submit_requires_the_minimum_record_and_pulls_back_to_draft_on_edit(fake):
    _, a = call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum'})
    tid = a['tree']['id']
    status, out = call('POST', 'tree_submit', 'tok-a', {'id': tid})
    assert status == 422 and set(out['missing']) == {'height_cm', 'width_cm', 'photo'}
    call('POST', 'tree_save', 'tok-a', {'id': tid, 'height_cm': 460, 'width_cm': 380})
    _, s = call('POST', 'media_sign', 'tok-a', {'tree_id': tid, 'mime': 'image/jpeg', 'bytes': 10})
    fake.objects[('mei-vault', s['path'])] = (10, 'image/jpeg')
    call('POST', 'media_commit', 'tok-a', {'tree_id': tid, 'path': s['path'], 'kind': 'photo', 'shot_no': 1, 'season': 'autumn'})
    status, out = call('POST', 'tree_submit', 'tok-a', {'id': tid})
    assert status == 200 and out['tree']['status'] == 'review'
    assert call('POST', 'tree_submit', 'tok-a', {'id': tid})[0] == 409
    status, out = call('POST', 'tree_save', 'tok-a', {'id': tid, 'given_name_ja': '紅雨'})
    assert status == 200 and out['tree']['status'] == 'draft', 'editing after 提出 returns the tree to draft'
    fake.tables['trees'][0]['status'] = 'published'
    assert call('POST', 'tree_save', 'tok-a', {'id': tid, 'given_name_ja': 'x'})[0] == 409, 'a published tree is read-only for the supplier'


def test_species_propose_is_pending_and_deduplicated(fake):
    status, out = call('POST', 'species_propose', 'tok-a', {'ja_kanji': '木斛', 'ja_reading': 'モッコク'})
    assert status == 201 and out['species']['status'] == 'pending_zh' and out['species']['id'].startswith('pending-')
    status, out = call('POST', 'species_propose', 'tok-a', {'ja_kanji': '木斛'})
    assert status == 200 and out['existing'] is True
    assert call('POST', 'species_propose', 'tok-a', {'ja_kanji': ''})[0] == 400


def test_species_pick_list_falls_back_to_the_seed_when_the_registry_is_empty(fake):
    fake.tables['species'] = []
    status, out = call('GET', 'species_all', 'tok-a')
    assert status == 200 and len(out['species']) >= 30 and all(s['ja_kanji'] for s in out['species'])


def test_every_write_leaves_an_event(fake):
    call('POST', 'tree_save', 'tok-a', {'species_id': 'acer-palmatum'})
    assert [e for e in fake.tables['events'] if e['action'] == 'create' and e['subject_kind'] == 'tree']


def test_db_unconfigured_is_503_not_a_leak(fake, monkeypatch):
    monkeypatch.setattr(_db, 'SERVICE', '')
    status, out = call('GET', 'me', 'tok-a')
    assert status == 503 and 'error' in out
