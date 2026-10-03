"""Page locks (plan §3, §8): nothing Google-hosted on a public page except the DEV font link, no Drive hotlinks,
every page tagged with a language, the seal reads 名木, the plaque rule and the disclaimer line exist."""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = sorted(glob.glob(os.path.join(ROOT, '**', '*.html'), recursive=True))


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def test_pages_exist():
    names = {os.path.relpath(p, ROOT) for p in PAGES}
    assert {'index.html', 't/index.html', 'journey/index.html', 'legal/index.html'} <= names


def test_no_google_assets_except_dev_fonts():
    for p in PAGES:
        html = read(p)
        hosts = set(re.findall(r'https?://([a-z0-9.-]+)', html))
        bad = {h for h in hosts if 'google' in h or 'gstatic' in h or 'youtube' in h} - {'fonts.googleapis.com'}
        assert not bad, f'{p}: {bad}'
        assert 'drive.google.com' not in html


def test_every_page_declares_a_language_and_the_viewport():
    for p in PAGES:
        html = read(p)
        assert re.search(r'<html lang="(zh-Hans|ja|en)"', html), p
        assert 'name="viewport"' in html, p


def test_brand_is_meiboku():
    for p in PAGES:
        html = read(p)
        assert '>名木<' in html, f'{p}: the seal must read 名木'


def test_dev_font_link_is_marked_as_dev_only_on_the_home_page():
    assert 'DEV ONLY' in read(os.path.join(ROOT, 'index.html'))


def test_runtime_rules_in_js():
    js = read(os.path.join(ROOT, 'assets', 'mei.js'))
    assert 'FIXED_TRADE' in js and '不构成法律意见' in js, 'every export plaque ends with the fixed sentence'
    assert "PROVENANCE" in js and '关东名园出品' in js
    assert not re.search(r'garden_id|name_ja|plot_ref|area_text', js), 'no garden identity fields in the runtime'
    assert 'solarTerm' in js and '秋分' in js
