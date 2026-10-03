#!/usr/bin/env python3
"""Print the `mei.species` + `mei.species_trade` seed INSERTs from data/species.json, for the Rakusalab migration
ledger (supabase/migrations/*_mei_schema.sql). Run from the meiki checkout:  python3 scripts/gen_species_seed.py
The migration is the ONE ledger; this script only regenerates its seed block, never applies anything."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, 'data', 'species.json'), encoding='utf-8') as f:
    SPECIES = json.load(f)['species']


def q(v):
    if v is None or v == '':
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def species_sql():
    cols = ('id, latin, ja_kanji, ja_reading, zh_hans, zh_hant, en, category, false_friend, kanji_note, status, best_season, rank,\n'
            '  know_intro_zh, know_origin_zh, know_character_zh, know_culture_zh, know_growth_zh, know_care_zh, link_baike, link_wiki_ja, link_wiki_en, approved_at')
    rows = []
    for s in SPECIES:
        k = (s.get('knowledge') or {}).get('zh') or {}
        L = s.get('links') or {}
        rows.append('  (' + ', '.join([q(s['id']), q(s['latin']), q(s['ja']), q(s['ja_reading']), q(s['zh']), q(s.get('zht')), q(s['en']), q(s['category']), q(bool(s.get('false_friend'))),
                                       q(s.get('kanji_note')), q('approved'), q(s['best_season']), q(s['rank']),
                                       q(k.get('intro')), q(k.get('origin')), q(k.get('character')), q(k.get('culture')), q(k.get('growth')), q(k.get('care')),
                                       q(L.get('baike')), q(L.get('wiki_ja')), q(L.get('wiki_en')), 'now()']) + ')')
    return 'insert into mei.species (' + cols + ') values\n' + ',\n'.join(rows) + '\non conflict (id) do nothing;'


def trade_sql():
    rows = []
    for s in SPECIES:
        t = (s.get('trade') or {}).get('CN') or {}
        rows.append('  (' + ', '.join([q(s['id']), q('CN'), q(t.get('status') or 'unknown'), q(t.get('note_staff')), q('docs/MEI_RESEARCH_2026-10-02.md §A'),
                                       q((t.get('verified_at') or '2026-10') + ('-02' if len(t.get('verified_at') or '') == 7 else ''))]) + ')')
    return 'insert into mei.species_trade (species_id, destination, status, fact_zh, source_ref, verified_at) values\n' + ',\n'.join(rows) + '\non conflict (species_id, destination) do nothing;'


if __name__ == '__main__':
    print(species_sql())
    print()
    print(trade_sql())
