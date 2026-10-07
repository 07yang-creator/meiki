"""Desk (审) + published-gallery locks: desk actions are staff-only and publishing admin-only; the publish gate blocks an
incomplete tree; publishing copies media vault → public INSIDE Storage and the public `trees` read then shows the real
tree first, in the sample shape, with no garden or internal field; send-back notes reach the supplier; sample photos
are replaced through a signed upsert and a manifest; public reads survive an unreachable database."""
import os
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'api'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _db                                    # noqa: E402
import mei as api                             # noqa: E402
from fake_supabase import FakeSupabase        # noqa: E402

GARDEN = str(uuid.uuid4())
SUP = {'id': str(uuid.uuid4()), 'email': 'a@garden.jp'}
STAFF = {'id': str(uuid.uuid4()), 'email': 'staff@mei'}
ADMIN = {'id': str(uuid.uuid4()), 'email': 'admin@mei'}
TOKENS = {'tok-sup': SUP, 'tok-staff': STAFF, 'tok-admin': ADMIN}
PRIVATE = ('garden_id', 'plot_ref', 'supplier_notes_ja', 'internal_ask_jpy', 'internal_notes')


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase()
    f.tables['gardens'] = [{'id': GARDEN, 'name_ja': '○○園'}]
    f.tables['members'] = [
        {'user_id': SUP['id'], 'role': 'supplier', 'garden_id': GARDEN, 'name': 'A', 'active': True},
        {'user_id': STAFF['id'], 'role': 'staff', 'garden_id': None, 'name': 'S', 'active': True},
        {'user_id': ADMIN['id'], 'role': 'admin', 'garden_id': None, 'name': 'M', 'active': True},
    ]
    f.tables['species'] = [{'id': 'acer-palmatum', 'latin': 'Acer palmatum', 'ja_kanji': '紅葉', 'zh_hans': '鸡爪槭（日本红枫）', 'status': 'approved', 'rank': 5, 'best_season': 'autumn'}]
    f.tables['species_trade'] = [{'species_id': 'acer-palmatum', 'destination': 'CN', 'status': 'permit_required', 'verified_at': '2026-10-02'}]
    _db.set_transport(f)
    monkeypatch.setattr(_db, 'SUPABASE_URL', 'https://fake.supabase.co')
    monkeypatch.setattr(_db, 'SERVICE', 'service-key')
    monkeypatch.setattr(api, 'VERIFY', lambda tok: TOKENS.get(tok))
    yield f
    _db.set_transport(_db.UrllibTransport())


def call(method, action, token=None, body=None, **qs):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    return api.dispatch(method, action, headers, {k: [v] for k, v in qs.items()}, body)


def submitted_tree(fake, with_photo=True):
    """A supplier's tree with the minimum record, 提出済み."""
    _, a = call('POST', 'tree_save', 'tok-sup', {'species_id': 'acer-palmatum', 'height_cm': 460, 'width_cm': 380, 'given_name_ja': '紅雨', 'plot_ref': '北圃場3', 'supplier_notes_ja': '株立ち六本。'})
    tid = a['tree']['id']
    if with_photo:
        _, s = call('POST', 'media_sign', 'tok-sup', {'tree_id': tid, 'mime': 'image/jpeg', 'bytes': 1234})
        fake.objects[('mei-vault', s['path'])] = (1234, 'image/jpeg')
        call('POST', 'media_commit', 'tok-sup', {'tree_id': tid, 'path': s['path'], 'kind': 'photo', 'shot_no': 1, 'season': 'autumn', 'taken_at': '2026-09-28'})
    assert call('POST', 'tree_submit', 'tok-sup', {'id': tid})[0] == (200 if with_photo else 422)
    return tid


def test_desk_actions_are_staff_only_and_publishing_admin_only(fake):
    tid = submitted_tree(fake)
    for method, action, body in (('GET', 'queue', None), ('GET', 'publish_check', None), ('GET', 'species_pending', None),
                                 ('POST', 'tree_set', {'id': tid, 'tier': 'signature'}), ('POST', 'tree_text_save', {'id': tid, 'lang': 'zh', 'body': 'x'}),
                                 ('POST', 'tree_sendback', {'id': tid, 'note': 'x'}), ('POST', 'sample_sign', {'sample_id': 'hong-yu', 'shot': 1, 'season': 'autumn', 'mime': 'image/jpeg', 'bytes': 10}),
                                 ('POST', 'sample_commit', {'sample_id': 'hong-yu', 'shot': 1, 'season': 'autumn'})):
        assert call(method, action, 'tok-sup', body, id=tid)[0] == 403, action
    assert call('POST', 'tree_publish', 'tok-staff', {'id': tid})[0] == 403
    assert call('POST', 'species_approve', 'tok-staff', {'id': 'x'})[0] == 403
    assert call('GET', 'queue', 'tok-staff')[0] == 200


def test_queue_lists_submitted_trees_with_garden_species_and_media_counts(fake):
    tid = submitted_tree(fake)
    status, out = call('GET', 'queue', 'tok-staff')
    assert status == 200 and [t['id'] for t in out['trees']] == [tid]
    t = out['trees'][0]
    assert t['garden'] == '○○園' and t['species_ja'] == '紅葉' and t['species_zh'].startswith('鸡爪槭') and t['photos'] == 1 and t['videos'] == 0
    assert out['totals'] == {'review': 1}
    assert call('GET', 'queue', 'tok-staff', status='published')[1]['trees'] == []
    assert call('GET', 'queue', 'tok-staff', status='bogus')[0] == 400


def test_publish_gate_then_publish_copies_media_and_the_gallery_shows_the_real_tree_first(fake):
    tid = submitted_tree(fake)
    status, gate = call('GET', 'publish_check', 'tok-staff', id=tid)
    assert status == 200 and gate['ready'] is False
    assert {i['key'] for i in gate['items'] if i['required'] and not i['ok']} == {'text_zh'}
    assert call('POST', 'tree_publish', 'tok-admin', {'id': tid})[0] == 422, 'the gate blocks publishing'
    status, tx = call('POST', 'tree_text_save', 'tok-staff', {'id': tid, 'lang': 'zh', 'headline': '六干并立', 'body': '株立ち六干，秋色自上而下。'})
    assert status == 201 and tx['text']['source'] == 'human'
    assert call('GET', 'publish_check', 'tok-staff', id=tid)[1]['ready'] is True
    call('POST', 'tree_set', 'tok-staff', {'id': tid, 'tier': 'signature', 'given_name_zh': '红雨', 'given_name_en': 'Red Rain'})
    status, out = call('POST', 'tree_publish', 'tok-admin', {'id': tid})
    assert status == 200 and out['tree']['status'] == 'published' and len(out['copied']) == 1 and out['skipped'] == []
    media = fake.tables['tree_media'][0]
    assert media['public_path'] == f"{out['tree']['catalog_no']}/{media['path'].rsplit('/', 1)[1]}"
    assert ('mei-public', media['public_path']) in fake.objects, 'the copy happened inside Storage'
    assert not any(m == 'GET' and '/storage/v1/object/mei-vault' in u for m, u in fake.calls), 'no bytes streamed through the function'
    # the public read: real tree first, sample shape, no private field
    status, pub = call('GET', 'trees')
    assert status == 200 and pub['public_base'].endswith('/storage/v1/object/public/mei-public/')
    first = pub['trees'][0]
    assert first['real'] is True and first['id'] == out['tree']['slug'] and first['tier'] == 'signature'
    assert first['given_name'] == {'zh': '红雨', 'ja': '紅雨', 'en': 'Red Rain'} and first['species'] == 'acer-palmatum'
    assert first['measures']['height_cm'] == 460 and first['text']['zh']['headline'] == '六干并立'
    assert first['photos'][0]['shot'] == 1 and first['photos'][0]['season'] == 'autumn' and first['photos'][0]['src'].startswith(pub['public_base'])
    assert not any(k in first for k in PRIVATE)
    assert all(t.get('sample') for t in pub['trees'][1:]), 'samples trail the real trees'
    status, one = call('GET', 'tree', slug=first['id'])
    assert status == 200 and one['tree']['catalog_no'] == out['tree']['catalog_no']
    # the supplier may no longer edit; staff may mark it reserved; re-publishing is idempotent on media
    assert call('POST', 'tree_save', 'tok-sup', {'id': tid, 'height_cm': 1})[0] == 409
    assert call('POST', 'tree_set', 'tok-staff', {'id': tid, 'status': 'reserved'})[1]['tree']['status'] == 'reserved'
    assert call('POST', 'tree_set', 'tok-staff', {'id': tid, 'status': 'withdrawn'})[0] == 403
    assert call('POST', 'tree_set', 'tok-admin', {'id': tid, 'status': 'withdrawn'})[1]['tree']['status'] == 'withdrawn'
    assert call('GET', 'trees')[1]['trees'][0].get('sample'), 'a withdrawn tree leaves the gallery'
    status, again = call('POST', 'tree_publish', 'tok-admin', {'id': tid})
    assert status == 200 and again['copied'] == [] and again['tree']['published_at'] == out['tree']['published_at']


def test_tree_set_refuses_states_before_the_first_publish_and_validates(fake):
    tid = submitted_tree(fake)
    assert call('POST', 'tree_set', 'tok-staff', {'id': tid, 'status': 'reserved'})[0] == 409
    assert call('POST', 'tree_set', 'tok-staff', {'id': tid, 'tier': 'legendary'})[0] == 400
    assert call('POST', 'tree_set', 'tok-staff', {'id': tid})[0] == 400
    assert call('POST', 'tree_set', 'tok-staff', {'id': tid, 'given_name_zh': 42})[0] == 400
    status, out = call('POST', 'tree_set', 'tok-staff', {'id': tid, 'sort_weight': 5000, 'best_season_override': 'spring'})
    assert status == 200 and out['tree']['sort_weight'] == 1000 and out['tree']['best_season_override'] == 'spring'


def test_sendback_returns_the_tree_to_draft_and_the_supplier_reads_the_note(fake):
    tid = submitted_tree(fake)
    assert call('POST', 'tree_sendback', 'tok-staff', {'id': tid, 'note': ''})[0] == 400
    status, out = call('POST', 'tree_sendback', 'tok-staff', {'id': tid, 'note': '⑥根元の写真をお願いします。'})
    assert status == 200 and out['tree']['status'] == 'draft'
    status, got = call('GET', 'tree_get', 'tok-sup', id=tid)
    assert status == 200 and got['sendback'] == '⑥根元の写真をお願いします。'
    assert 'texts' not in got and 'garden' not in got, 'the supplier view carries no desk extras'
    status, staff_view = call('GET', 'tree_get', 'tok-staff', id=tid)
    assert staff_view['garden']['name_ja'] == '○○園' and staff_view['texts'] == []
    assert call('POST', 'tree_sendback', 'tok-staff', {'id': tid, 'note': 'x'})[0] == 200, 'a draft can be annotated again'


def test_media_urls_signs_vault_objects_and_uses_public_urls_after_publish(fake):
    tid = submitted_tree(fake)
    status, out = call('GET', 'media_urls', 'tok-sup', id=tid)
    assert status == 200 and out['media'][0]['url'].startswith('https://fake.supabase.co/storage/v1/object/sign/mei-vault/')
    call('POST', 'tree_text_save', 'tok-staff', {'id': tid, 'lang': 'zh', 'body': 'x'})
    call('POST', 'tree_publish', 'tok-admin', {'id': tid})
    status, out = call('GET', 'media_urls', 'tok-staff', id=tid)
    assert out['media'][0]['url'].startswith('https://fake.supabase.co/storage/v1/object/public/mei-public/')


def test_species_approval_is_admin_only_and_needs_zh_and_a_binomial(fake):
    _, prop = call('POST', 'species_propose', 'tok-sup', {'ja_kanji': '木斛', 'ja_reading': 'モッコク'})
    sid = prop['species']['id']
    status, pend = call('GET', 'species_pending', 'tok-staff')
    assert status == 200 and [s['id'] for s in pend['species']] == [sid]
    assert call('POST', 'species_approve', 'tok-admin', {'id': sid, 'zh_hant': '厚皮香'})[0] == 400
    assert call('POST', 'species_approve', 'tok-admin', {'id': sid, 'zh_hant': '厚皮香', 'latin': 'mokkoku tree'})[0] == 400
    assert call('POST', 'species_approve', 'tok-admin', {'id': sid, 'zh_hant': '厚皮香', 'latin': 'Acer palmatum'})[0] == 409, 'Latin is the unique join key'
    status, out = call('POST', 'species_approve', 'tok-admin', {'id': sid, 'zh_hant': '厚皮香', 'latin': 'Ternstroemia gymnanthera', 'en': 'Japanese ternstroemia', 'category': 'evergreen', 'best_season': 'summer', 'rank': 20})
    assert status == 200 and out['species']['status'] == 'approved' and out['species']['rank'] == 20
    assert out['species']['zh_hant'] == '厚皮香' and not out['species'].get('zh_hans'), 'the desk types the 繁體 name (ruling 17)'
    status, pub = call('GET', 'species')
    extra = [x for x in pub['species'] if x['id'] == sid][0]
    assert extra['zh'] == '厚皮香' and extra['trade']['CN']['status'] == 'unknown', 'an approved extra species reaches the public read with its 繁體 name'
    assert call('POST', 'species_approve', 'tok-admin', {'id': 'nope', 'zh_hant': 'x', 'latin': 'Abies firma'})[0] == 404
    assert call('GET', 'species_pending', 'tok-staff')[1]['species'] == []


def test_sample_photo_replacement_signs_an_upsert_and_feeds_the_manifest_into_public_trees(fake):
    assert call('POST', 'sample_sign', 'tok-staff', {'sample_id': 'nope', 'shot': 1, 'season': 'autumn', 'mime': 'image/jpeg', 'bytes': 10})[0] == 404
    assert call('POST', 'sample_sign', 'tok-staff', {'sample_id': 'hong-yu', 'shot': 11, 'season': 'autumn', 'mime': 'image/jpeg', 'bytes': 10})[0] == 400
    assert call('POST', 'sample_sign', 'tok-staff', {'sample_id': 'hong-yu', 'shot': 1, 'season': 'autumn', 'mime': 'image/png', 'bytes': 10})[0] == 400
    status, s = call('POST', 'sample_sign', 'tok-staff', {'sample_id': 'hong-yu', 'shot': 1, 'season': 'autumn', 'mime': 'image/jpeg', 'bytes': 10})
    assert status == 200 and s['bucket'] == 'mei-public' and s['path'] == 'samples/hong-yu/1-autumn.jpg'
    assert fake.sign_headers[-1].get('x-upsert') == 'true', 'replacing a sample must be an upsert'
    assert call('POST', 'sample_commit', 'tok-staff', {'sample_id': 'hong-yu', 'shot': 1, 'season': 'autumn'})[0] == 409
    fake.objects[('mei-public', s['path'])] = (10, 'image/jpeg')
    status, c = call('POST', 'sample_commit', 'tok-staff', {'sample_id': 'hong-yu', 'shot': 1, 'season': 'autumn'})
    assert status == 200 and c['src'].startswith('https://fake.supabase.co/storage/v1/object/public/mei-public/samples/hong-yu/1-autumn.jpg?v=')
    manifest = fake.json_objects[('mei-public', 'samples/manifest.json')]
    assert manifest['hong-yu']['1-autumn']['p'] == 'samples/hong-yu/1-autumn.jpg'
    status, pub = call('GET', 'trees')
    hy = [t for t in pub['trees'] if t['id'] == 'hong-yu'][0]
    front = [p for p in hy['photos'] if p['shot'] == 1 and p['season'] == 'autumn'][0]
    assert front['src'] == c['src']
    assert not any(p.get('src') for p in hy['photos'] if not (p['shot'] == 1 and p['season'] == 'autumn')), 'only the replaced shot carries a src'
    assert [e for e in fake.tables['events'] if e['action'] == 'sample_photo']


def test_public_reads_survive_an_unreachable_database(fake, monkeypatch):
    class Dead:
        def request(self, *a, **k):
            raise OSError('network down')
    _db.set_transport(Dead())
    status, out = call('GET', 'trees')
    assert status == 200 and len(out['trees']) >= 10 and all(t.get('sample') for t in out['trees'])
    assert call('GET', 'species')[0] == 200
    assert call('GET', 'tree', slug='hong-yu')[0] == 200
