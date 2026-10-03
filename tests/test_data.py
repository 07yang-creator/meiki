"""Data locks for the 名木 Mei seed (plan §6, §7, ruling 2): the registry and the sample trees obey the rules
before any page renders them. Run: pytest mei/tests (from the Rakusalab checkout) or pytest (from the mei repo)."""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'api'))


def load(name):
    with open(os.path.join(ROOT, 'data', name), encoding='utf-8') as f:
        return json.load(f)


SPECIES = load('species.json')['species']
TREES = load('trees.json')['trees']
BY_ID = {s['id']: s for s in SPECIES}
SEASONS = {'spring', 'summer', 'autumn', 'winter'}
TRADE = {'prohibited', 'no_condition', 'protocol', 'permit_required', 'cites', 'unknown'}
# Japanese-only kanji / glyph forms that must never appear in a Chinese name (plan §6 leak table)
JA_LEAK = re.compile('[黒桜樹齢歳鉢検鉄犀楓槇槙欅樫椿躑躅楢檜]')   # 榧 · 柊 are legitimate ZH characters (日本榧树 · 柊树)
GARDEN_WORDS = re.compile('(園|庭園|氏|先生|吉岡|農場)')


def test_latin_is_unique_join_key():
    latins = [s['latin'] for s in SPECIES]
    assert len(latins) == len(set(latins)), 'Latin binomial must be unique'
    assert all(re.match(r'^[A-Z][a-z]+( [a-z\.]+)+', l) for l in latins)


def test_species_fields_and_seasons():
    for s in SPECIES:
        assert s['best_season'] in SEASONS, s['id']
        assert isinstance(s['rank'], int) and s['rank'] > 0
        assert s['zh'] and s['ja'] and s['en'], s['id']
        assert s['trade']['CN']['status'] in TRADE, s['id']


def test_chinese_names_carry_no_japanese_glyphs():
    # the one tolerated exception: 真柏 is the term Chinese bonsai circles use (seed note)
    for s in SPECIES:
        zh = s['zh'].replace('真柏', '')
        assert not JA_LEAK.search(zh), f"{s['id']}: ZH name {s['zh']} carries a Japanese form"


def test_false_friends_are_flagged_as_data():
    ff = {s['ja'][:1] for s in SPECIES if s['false_friend']}
    for must in ('椿', '楓', '紅', '槇', '杉', '檜'):
        assert any(k.startswith(must) for k in ff) or any(s['ja'].startswith(must) and s['false_friend'] for s in SPECIES), must


def test_pines_are_prohibited_for_china():
    for s in SPECIES:
        if s['latin'].startswith('Pinus'):
            assert s['trade']['CN']['status'] == 'prohibited', s['id']


def test_trees_reference_species_and_valid_fields():
    for t in TREES:
        assert t['species'] in BY_ID, t['id']
        assert t['tier'] in ('signature', 'collection', 'stock')
        assert t['status'] in ('draft', 'review', 'published', 'reserved', 'sold', 'withdrawn')
        assert re.match(r'^MEI-\d{4}-\d{3}$', t['catalog_no'])
        assert t.get('best_season') in SEASONS | {None}
        for p in t.get('photos', []):
            assert p['season'] in SEASONS and re.match(r'^\d{4}-\d{2}-\d{2}$', p['taken_at'])


def test_catalog_numbers_unique():
    nos = [t['catalog_no'] for t in TREES]
    assert len(nos) == len(set(nos))


def test_every_published_tree_has_a_best_season_photo():
    for t in TREES:
        if t['status'] != 'published':
            continue
        season = t.get('best_season') or BY_ID[t['species']]['best_season']
        assert any(p['shot'] == 1 and p['season'] == season for p in t['photos']), f"{t['catalog_no']} lacks its 見頃 hero"


def test_public_texts_never_name_a_garden_or_a_price():
    price = re.compile('(万円|円|¥|元|人民币|价格|報价|报价|議価|议价)')
    for t in TREES:
        for lang, tx in (t.get('text') or {}).items():
            for v in tx.values():
                assert not GARDEN_WORDS.search(v or ''), f"{t['catalog_no']} {lang}: garden word"
                assert not price.search(v or ''), f"{t['catalog_no']} {lang}: price word"
        for k in ('garden_id', 'plot_ref', 'internal_ask_jpy', 'internal_notes'):
            assert k not in t, f'{k} must not exist in the public seed'


def test_api_public_read_strips_private_fields():
    import mei as api
    trees = api.public_trees()
    assert trees and all(t['status'] in api.PUBLIC_STATUSES for t in trees)
    for t in trees:
        for k in ('garden_id', 'plot_ref', 'internal_ask_jpy', 'internal_notes', 'supplier_notes_ja'):
            assert k not in t
    species = api.public_species()
    assert all('note_staff' not in s['trade']['CN'] for s in species)
    assert api.handle('tree', {'slug': ['hong-yu']})[0] == 200
    assert api.handle('tree', {'slug': ['nope']})[0] == 404
    assert api.handle('bogus', {})[0] == 404


def test_every_species_has_an_intro_and_reading_links():
    for s in SPECIES:
        k = (s.get('knowledge') or {}).get('zh') or {}
        assert k.get('intro') and len(k['intro']) <= 120, f"{s['id']}: a one-sentence 中文 intro"
        for key in ('origin', 'character', 'culture', 'growth', 'care'):
            assert k.get(key), f"{s['id']}: knowledge.{key}"
        links = s.get('links') or {}
        assert links.get('wiki_en', '').startswith('https://en.wikipedia.org/wiki/'), s['id']
        assert links.get('wiki_ja', '').startswith('https://ja.wikipedia.org/wiki/'), s['id']
        assert links.get('baike', '').startswith('https://baike.baidu.com/item/'), s['id']
        # a Japanese term QUOTED in 「」 to explain it is fine; a Japanese glyph in running Chinese is a leak
        assert not JA_LEAK.search(re.sub('「[^」]*」', '', k['intro']).replace('真柏', '')), f"{s['id']}: the intro carries a Japanese glyph"
