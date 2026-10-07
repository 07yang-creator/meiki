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
    assert {'index.html', 't/index.html', 'journey/index.html', 'legal/index.html', 'in/index.html', 'login/index.html', 'desk/index.html'} <= names


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
        assert re.search(r'<html lang="(zh-Hant|ja|en)"', html), f'{p}: Chinese pages are Traditional (ruling 17)'
        assert 'name="viewport"' in html, p


def test_brand_is_meiboku():
    for p in PAGES:
        html = read(p)
        assert '>名木<' in html, f'{p}: the seal must read 名木'


def test_dev_font_link_is_marked_as_dev_only_on_the_home_page():
    assert 'DEV ONLY' in read(os.path.join(ROOT, 'index.html'))


def test_runtime_rules_in_js():
    js = read(os.path.join(ROOT, 'assets', 'mei.js'))
    assert 'FIXED_TRADE' in js and '不構成法律意見' in js, 'every export plaque ends with the fixed sentence'
    assert "PROVENANCE" in js and '關東名園出品' in js
    assert not re.search(r'garden_id|name_ja|plot_ref|area_text', js), 'no garden identity fields in the runtime'
    assert 'solarTerm' in js and '秋分' in js


def test_member_pages_are_noindex_and_load_auth_before_their_script():
    for rel in ('in/index.html', 'login/index.html', 'desk/index.html'):
        html = read(os.path.join(ROOT, rel))
        assert 'name="robots" content="noindex"' in html, rel
        assert html.index('assets/auth.js') < len(html), rel
        assert 'requireLogin' in html or 'intake.js' in html or 'desk.js' in html, rel


def test_every_public_page_has_the_member_entrance_and_login_routes_by_role():
    for rel in ('index.html', 't/index.html', 'journey/index.html', 'legal/index.html'):
        html = read(os.path.join(ROOT, rel))
        assert re.search(r'href="(\.\./)?login/"[^>]*>メンバー<', html), f'{rel}: footer 「メンバー」 → login'
    login = read(os.path.join(ROOT, 'login', 'index.html'))
    assert "'../in/'" in login and "'../desk/'" in login and 'sameOriginPath' in login
    assert login.count('location.replace') == 1, 'exactly one redirect'


def test_gallery_runtime_reads_the_api_first_and_falls_back_to_files():
    js = read(os.path.join(ROOT, 'assets', 'mei.js'))
    assert 'api/mei?action=trees' in js and 'data/trees.json' in js
    assert 'laceEdge' in js and 'lace' in js and 'wave' not in js.replace('waves', ''), 'section breaks are lace now'
    assert '延伸閱讀' in js and 'rel="noopener noreferrer"' in js and 'target="_blank"' in js
    assert 'edit-slot' in js and 'assets/edit.js' in js
    edit = read(os.path.join(ROOT, 'assets', 'edit.js'))
    assert 'sample_sign' in edit and 'sample_commit' in edit and "'x-upsert': 'true'" in edit
    desk = read(os.path.join(ROOT, 'assets', 'desk.js'))
    for action in ('queue', 'publish_check', 'tree_publish', 'tree_sendback', 'tree_text_save', 'tree_set', 'species_approve', 'media_urls'):
        assert action in desk, action


def test_no_google_assets_except_dev_fonts_and_supabase_cdn_only_in_auth():
    js = read(os.path.join(ROOT, 'assets', 'mei.js'))
    assert 'cdn.jsdelivr.net' not in js, 'the public gallery runtime loads no third-party script'
    auth = read(os.path.join(ROOT, 'assets', 'auth.js'))
    assert 'supabase-js@2' in auth


SIMPLIFIED_ONLY = re.compile('[这为树种实际价询预约录发现关东园陆选学长经时让体对将认记录义变产标过兴见节观赏树龄爱页审订线阅维链]')
# the same set without the three characters Japanese shinjitai shares (体 学 将): safe on a lang="ja" page
SIMPLIFIED_NOT_JAPANESE = re.compile('[这为树种实际价询预约录发现关东园陆选长经时让对认记录义变产标过兴见节观赏树龄爱页审订线阅维链]')


def test_chinese_ui_is_traditional():
    """Ruling 17 (2026-10-07): 全部使用繁體字. Simplified-only characters may not appear in any Chinese UI string —
    text, attributes (aria-label, onsubmit) and script literals alike."""
    for rel in ('index.html', 't/index.html', 'journey/index.html', 'desk/index.html'):
        html = read(os.path.join(ROOT, rel))
        body = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        assert not SIMPLIFIED_ONLY.search(body), f"{rel}: {SIMPLIFIED_ONLY.search(body).group(0)}"
    for rel in ('legal/index.html', 'login/index.html', 'in/index.html'):
        html = read(os.path.join(ROOT, rel))
        body = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        assert not SIMPLIFIED_NOT_JAPANESE.search(body), f"{rel}: {SIMPLIFIED_NOT_JAPANESE.search(body).group(0)}"
    for rel in ('assets/mei.js', 'assets/desk.js', 'assets/edit.js', 'assets/qr.js'):
        js = read(os.path.join(ROOT, rel))
        strings = ''.join(re.findall(r"'((?:[^'\\\n]|\\.)*)'", js))
        assert not SIMPLIFIED_ONLY.search(strings), f"{rel}: {SIMPLIFIED_ONLY.search(strings).group(0)}"


def font_families(html):
    link = re.search(r'fonts\.googleapis\.com/css2\?([^"]*)"', html)
    return set(re.findall(r'family=([^:&]+)', link.group(1))) if link else set()


def test_chinese_faces_carry_the_traditional_glyph_set():
    """Owner, 2026-10-07: 消除字體不一致. Ma Shan Zheng (the brush) has no glyphs for most Traditional-only characters,
    so a 繁體 title set in it rendered half brush, half fallback serif. Every Chinese face is now a TC face; the brush
    keeps only the wordmark and the season kanji (see the test below)."""
    css = read(os.path.join(ROOT, 'assets', 'mei.css'))
    assert re.search(r'--f-dzh:\s*"LXGW WenKai TC", "Noto Serif TC"', css), 'Chinese titles: 楷 with the full 繁體 set'
    assert re.search(r'--f-serif:\s*"Noto Serif TC"', css), 'Chinese serif: TC'
    assert re.search(r'--f-brush:\s*"Ma Shan Zheng", "LXGW WenKai TC"', css), 'the brush falls back to the same 楷, never a serif'
    assert re.search(r'--f-sans:[^;]*"PingFang TC"', css) and 'Noto Sans CJK TC' in css
    assert '.text p:lang(ja)' in css, 'a Japanese paragraph in the tree text keeps the JP serif (the .text p rule outranks :lang(ja))'
    for face in ('Noto Serif SC', 'PingFang SC', 'Noto Sans CJK SC', 'Microsoft YaHei'):
        assert face not in css, face
    renders_titles = {'index.html', 't/index.html', 'journey/index.html', 'desk/index.html'}   # class="dzh" or mei.js / desk.js
    for p in PAGES:
        rel = os.path.relpath(p, ROOT)
        html = read(p)
        fams = font_families(html)
        assert not fams & {'Noto+Serif+SC', 'ZCOOL+XiaoWei'}, f'{rel}: Simplified-only faces requested: {fams}'
        if rel in renders_titles:
            assert {'LXGW+WenKai+TC', 'Noto+Serif+TC'} <= fams, f'{rel}: {fams}'
        if 'class="brush' in html:
            assert 'Ma+Shan+Zheng' in fams, f'{rel}: the wordmark needs the brush'


BRUSH_GLYPHS = set('名木春夏秋冬')


def test_the_brush_only_draws_glyphs_it_has():
    """The brush face covers GB 2312 only. Whatever sits in a .brush span must be the wordmark or a season kanji."""
    for p in PAGES:
        for inner in re.findall(r'class="brush[^"]*"[^>]*>([^<]*)<', read(p)):
            assert set(inner.strip()) <= BRUSH_GLYPHS, f'{os.path.relpath(p, ROOT)}: {inner!r}'
    js = read(os.path.join(ROOT, 'assets', 'mei.js'))
    for expr in re.findall(r'class="brush[^"]*"[^>]*>\' \+ ([A-Za-z_.\[\]]+)', js):
        assert expr.endswith('.kanji'), f'a .brush span renders {expr}, not a season kanji'
    assert set(re.findall(r"kanji: '(.)'", js)) <= BRUSH_GLYPHS
