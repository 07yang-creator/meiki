#!/usr/bin/env python3
"""fetch_samples.py — pull SAMPLE photos per species from Wikimedia Commons (public-domain / CC0 only) for the
design preview, write data/samples/<species>-<season>.jpg + data/samples/ATTRIBUTION.md, and point the sample
trees' hero photos at them.

Why a script: the cloud session that built the site cannot reach wikimedia.org (network policy), so the owner
runs this once on a machine that can:   python3 scripts/fetch_samples.py  [--dry-run]

Only files whose Commons licence is Public domain / CC0 are taken (no attribution duty, nothing to get wrong on a
commercial site); everything else is skipped and listed. These are stand-ins: the garden's own 10-shot sets
replace them (plan §15), so nothing here is ever a tree the site sells.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'samples')
API = 'https://commons.wikimedia.org/w/api.php'
UA = 'mei-sample-fetcher/0.1 (+https://mei.rakusalab.com; design preview placeholders)'
FREE = re.compile(r'(public domain|cc0|pd-)', re.I)

QUERIES = {  # species id → search phrase; season words nudge the picker toward the 見頃
    'acer-palmatum': 'Acer palmatum tree autumn garden Japan',
    'pinus-thunbergii': 'Pinus thunbergii garden tree Japan',
    'pinus-parviflora': 'Pinus parviflora garden tree',
    'podocarpus-macrophyllus': 'Podocarpus macrophyllus garden tree Japan',
    'juniperus-chinensis-sargentii': 'Juniperus chinensis sargentii bonsai',
    'camellia-japonica': 'Camellia japonica tree flowering',
    'zelkova-serrata': 'Zelkova serrata autumn tree',
    'osmanthus-fragrans-aurantiacus': 'Osmanthus fragrans aurantiacus flowering',
    'prunus-mume-pendula': 'weeping Prunus mume tree flowering',
    'cerasus-itosakura': 'shidarezakura weeping cherry tree',
    'prunus-mume': 'Prunus mume tree flowering Japan',
    'rhododendron-indicum': 'Rhododendron indicum satsuki flowering',
    'quercus-myrsinifolia': 'Quercus myrsinifolia tree',
    'lagerstroemia-indica': 'Lagerstroemia indica tree flowering',
    'cinnamomum-camphora': 'Cinnamomum camphora large tree Japan',
    'chamaecyparis-obtusa': 'Chamaecyparis obtusa tree',
    'osmanthus-heterophyllus': 'Osmanthus heterophyllus shrub',
    'gardenia-jasminoides': 'Gardenia jasminoides flowering',
    'ternstroemia-gymnanthera': 'Ternstroemia gymnanthera tree',
    'taxus-cuspidata': 'Taxus cuspidata nana shrub',
}


def get(params):
    params = dict(params, format='json')
    req = urllib.request.Request(API + '?' + urllib.parse.urlencode(params), headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def candidates(query):
    res = get({'action': 'query', 'generator': 'search', 'gsrsearch': query, 'gsrnamespace': 6, 'gsrlimit': 12,
               'prop': 'imageinfo', 'iiprop': 'url|extmetadata|size|mime', 'iiurlwidth': 1600})
    for page in (res.get('query', {}).get('pages') or {}).values():
        ii = (page.get('imageinfo') or [{}])[0]
        meta = ii.get('extmetadata') or {}
        lic = (meta.get('LicenseShortName') or {}).get('value', '')
        if not FREE.search(lic) or not ii.get('mime', '').startswith('image/jpeg'):
            continue
        if (ii.get('width') or 0) < 800:
            continue
        yield {'title': page['title'], 'url': ii.get('thumburl') or ii.get('url'), 'page': ii.get('descriptionurl'),
               'license': lic, 'artist': re.sub('<[^>]+>', '', (meta.get('Artist') or {}).get('value', '')).strip()}


def main(dry=False):
    os.makedirs(OUT, exist_ok=True)
    trees = json.load(open(os.path.join(ROOT, 'data', 'trees.json'), encoding='utf-8'))
    lines = ['# Sample photo attribution (design preview only)\n', 'All files Public domain / CC0 on Wikimedia Commons at fetch time; verify before any public deploy.\n']
    got = {}
    for sid, q in QUERIES.items():
        try:
            c = next(iter(candidates(q)), None)
        except Exception as e:
            print(f'{sid}: search failed ({type(e).__name__})'); continue
        if not c:
            print(f'{sid}: no free image found'); continue
        fn = f'{sid}.jpg'
        if not dry:
            req = urllib.request.Request(c['url'], headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r, open(os.path.join(OUT, fn), 'wb') as f:
                f.write(r.read())
            time.sleep(1)
        got[sid] = f'data/samples/{fn}'
        lines.append(f"- `{fn}` — {c['title']} · {c['license']} · {c['artist'] or 'unknown'} · {c['page']}")
        print(f'{sid}: {c["title"]} ({c["license"]})')
    if not dry:
        for t in trees['trees']:
            src = got.get(t['species'])
            if not src:
                continue
            for p in t.get('photos', []):
                if p['shot'] in (1, 2):
                    p['src'] = src
        json.dump(trees, open(os.path.join(ROOT, 'data', 'trees.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        open(os.path.join(OUT, 'ATTRIBUTION.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f'{len(got)} species with a sample photo')


if __name__ == '__main__':
    main(dry='--dry-run' in sys.argv)
