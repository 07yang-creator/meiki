/* mei.js — 名木 Mei public gallery runtime.
 * Data: GET api/mei?action=species|trees (the published REAL trees + the 20 samples, samples carrying replaced photos
 * from the public bucket); falls back to data/*.json when the API is unreachable (static preview). Renderers never
 * know which source fed them. Real trees (`real: true`) come first in every season; samples trail, tagged 示例.
 * Language: ?lang=zh|ja|en, remembered in localStorage('mei.lang'); zh is canonical, en optional per tree.
 * Season order: the current season first, then calendar order. Tree order inside a chapter:
 * real → tier (signature → collection → stock) → species.rank → sort_weight → published_at desc.
 * ?edit=1 (staff/admin): loads auth.js + edit.js and offers 「替换照片」 beside every sample photo (temporary).
 */
(function () {
  'use strict';
  var SEASONS = ['spring', 'summer', 'autumn', 'winter'];
  var SEASON = {
    spring: { kanji: '春', zh: '春', ja: '春', en: 'Spring', months: '3–5月', verb: '看花', sub: { zh: '花の季', en: 'SPRING' } },
    summer: { kanji: '夏', zh: '夏', ja: '夏', en: 'Summer', months: '6–8月', verb: '看绿', sub: { zh: '緑陰の季', en: 'SUMMER' } },
    autumn: { kanji: '秋', zh: '秋', ja: '秋', en: 'Autumn', months: '9–11月', verb: '看叶', sub: { zh: '紅葉の季', en: 'AUTUMN' } },
    winter: { kanji: '冬', zh: '冬', ja: '冬', en: 'Winter', months: '12–2月', verb: '看枝', sub: { zh: '常緑と枝の季', en: 'WINTER' } }
  };
  var TIER = { signature: { zh: '铭品', ja: '銘品', en: 'SIGNATURE' }, collection: { zh: '名木', ja: '名木', en: 'COLLECTION' }, stock: { zh: '庭木', ja: '庭木', en: 'GARDEN STOCK' } };
  var TRADE = {
    prohibited: { zh: '不可出口至中国大陆', ja: '中国本土への輸出不可', en: 'Not exportable to mainland China', sub: '中国进境植物检疫禁止进境物名录所列（松属 · 松材线虫）· 本株可在日本国内交付或出口至其他地区', short: '不可出口至中国大陆 · 仅限展示', arc: 'autumn' },
    no_condition: { zh: '出口条件待确认', ja: '輸出条件は確認中', en: 'Export conditions not established', sub: '需由进口方向中国海关申请许可并确认检疫条件', short: '出口条件待确认', arc: 'gold' },
    protocol: { zh: '出口条件待确认', ja: '輸出条件は確認中', en: 'Export conditions not established', sub: '日中议定书暂停中，需由进口方向中国海关确认', short: '出口条件待确认', arc: 'gold' },
    cites: { zh: '可申请出口（需 CITES 许可 · 进口许可 · 去土 · 隔离检疫）', ja: '輸出可（CITES・輸入許可・土壌除去・隔離検疫が必要）', en: 'Exportable with CITES and import permits', sub: '华盛顿公约附录 II；由进口方申请许可；根球去土；入境后隔离', short: '需 CITES 许可', arc: 'summer' },
    permit_required: { zh: '可申请出口（需进口许可 · 去土 · 隔离检疫）', ja: '輸出可（輸入許可・土壌除去・隔離検疫が必要）', en: 'Exportable with import permit', sub: '由进口方向中国海关申请许可；根球须去土或置换为合格介质；入境后在指定隔离场所隔离', short: '', arc: 'summer' },
    unknown: { zh: '出口条件待确认', ja: '輸出条件は確認中', en: 'Export conditions not established', sub: '需由进口方确认', short: '出口条件待确认', arc: 'gold' }
  };
  var FIXED_TRADE = '以上为植物检疫一般信息，不构成法律意见；具体以中国海关及日本植物防疫所的现行规定为准。';
  var PROVENANCE = { zh: '关东名园出品', ja: '関東の名園出品', en: 'From a distinguished Kantō garden' };
  // 二十四節気 — month/day boundaries (±1 day by year; display only)
  var TERMS = [[1, 5, '小寒'], [1, 20, '大寒'], [2, 4, '立春'], [2, 18, '雨水'], [3, 5, '啓蟄'], [3, 20, '春分'], [4, 5, '清明'], [4, 20, '穀雨'], [5, 5, '立夏'], [5, 21, '小満'], [6, 5, '芒種'], [6, 21, '夏至'], [7, 7, '小暑'], [7, 22, '大暑'], [8, 7, '立秋'], [8, 23, '処暑'], [9, 7, '白露'], [9, 23, '秋分'], [10, 8, '寒露'], [10, 23, '霜降'], [11, 7, '立冬'], [11, 22, '小雪'], [12, 7, '大雪'], [12, 22, '冬至']];

  function solarTerm(iso) {
    if (!iso) return '';
    var p = iso.split('-'); var m = +p[1], d = +(p[2] || 1);
    var cur = TERMS[TERMS.length - 1][2];
    for (var i = 0; i < TERMS.length; i++) { if (m > TERMS[i][0] || (m === TERMS[i][0] && d >= TERMS[i][1])) cur = TERMS[i][2]; }
    return cur;
  }
  function seasonOf(date) { var m = (date || new Date()).getMonth() + 1; return m >= 3 && m <= 5 ? 'spring' : m >= 6 && m <= 8 ? 'summer' : m >= 9 && m <= 11 ? 'autumn' : 'winter'; }
  function seasonOrder(current) { var i = SEASONS.indexOf(current); return SEASONS.slice(i).concat(SEASONS.slice(0, i)); }
  function nextTermLine(date) {
    var y = date.getFullYear();
    for (var i = 0; i < TERMS.length; i++) { var t = new Date(y, TERMS[i][0] - 1, TERMS[i][1]); if (t >= date) return TERMS[i][2] + ' ' + y + '-' + pad(TERMS[i][0]) + '-' + pad(TERMS[i][1]); }
    return TERMS[0][2] + ' ' + (y + 1) + '-01-05';
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  // ---- language / mode ----
  var Q = new URLSearchParams(location.search);
  var EDIT = Q.get('edit') === '1';
  var EDITQ = EDIT ? '&edit=1' : '';
  function getLang() {
    var q = Q.get('lang');
    var l = q || (safeGet('mei.lang')) || 'zh';
    if (['zh', 'ja', 'en'].indexOf(l) < 0) l = 'zh';
    if (q) safeSet('mei.lang', q);
    return l;
  }
  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { } }

  // ---- data ----
  var BASE = (document.querySelector('meta[name="mei-base"]') || {}).content || '/';
  function getJSON(url) { return fetch(url, { headers: { 'Accept': 'application/json' } }).then(function (r) { if (!r.ok) throw new Error(url + ' → ' + r.status); return r.json(); }); }
  function loadData() {
    var api = Promise.all([getJSON(BASE + 'api/mei?action=species'), getJSON(BASE + 'api/mei?action=trees')]).then(function (res) { return { species: res[0].species, trees: res[1].trees, note: '', source: 'api' }; });
    var files = function () { return Promise.all([getJSON(BASE + 'data/species.json'), getJSON(BASE + 'data/trees.json')]).then(function (res) { return { species: res[0].species, trees: res[1].trees, note: res[1].note, source: 'files' }; }); };
    return api.catch(files).then(function (raw) {
      var species = {}; raw.species.forEach(function (s) { species[s.id] = s; });
      var trees = raw.trees.map(function (t) {
        t.sp = species[t.species] || null;
        t.season = t.best_season || (t.sp && t.sp.best_season) || 'summer';
        t.rank = (t.sp && t.sp.rank) || 99;
        t.trade = (t.trade_override) || (t.sp && t.sp.trade && t.sp.trade.CN) || { status: 'unknown' };
        t.real = !!t.real; t.sample = !t.real && t.sample !== false;
        t.measures = t.measures || {}; t.form = t.form || { zh: '', ja: '', en: '' }; t.photos = t.photos || [];
        return t;
      });
      return { species: species, speciesList: raw.species, trees: trees, note: raw.note, source: raw.source, hasReal: trees.some(function (t) { return t.real; }) };
    });
  }
  var TIER_ORDER = { signature: 0, collection: 1, stock: 2 };
  function sortTrees(list) {
    return list.slice().sort(function (a, b) {
      return ((a.real ? 0 : 1) - (b.real ? 0 : 1)) || (TIER_ORDER[a.tier] - TIER_ORDER[b.tier]) || (a.rank - b.rank) || ((b.sort_weight || 0) - (a.sort_weight || 0)) || ((b.published_at || '') > (a.published_at || '') ? 1 : -1);
    });
  }

  // ---- formatting ----
  function m(cm) { return cm == null ? '—' : (cm / 100).toFixed(1).replace(/\.0$/, '') + ' m'; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function name(t, lang) { return t.given_name ? (t.given_name[lang] || t.given_name.zh || t.given_name.ja || '') : ''; }
  function speciesName(sp, lang) { if (!sp) return ''; return lang === 'ja' ? (sp.ja || '').replace(/（.*$/, '') : lang === 'en' ? sp.en : sp.zh; }
  function shortZh(sp) { return (sp && sp.zh ? sp.zh : '').replace(/（.*$/, ''); }
  function dateTerm(iso) { return iso ? '<span class="num">' + esc(iso.slice(5)) + ' · ' + solarTerm(iso) + '</span>' : ''; }
  function treeHref(t) { return BASE + 't/?slug=' + esc(t.id) + EDITQ; }
  var _uid = 0;
  function uid() { return 'o' + (++_uid); }

  // ---- ornaments ----
  var PAPER = '#F6F2EA';
  var ORN = {
    /* lace — the section break: hairlines fading in from both margins, a knot of interlaced loops at the centre */
    lace: function (color) {
      var g = uid();
      return '<svg class="orn lace" viewBox="0 0 320 20" aria-hidden="true"><defs>' +
        '<linearGradient id="' + g + 'l" x1="0" x2="1"><stop offset="0" stop-color="' + color + '" stop-opacity="0"/><stop offset="1" stop-color="' + color + '" stop-opacity="0.7"/></linearGradient>' +
        '<linearGradient id="' + g + 'r" x1="0" x2="1"><stop offset="0" stop-color="' + color + '" stop-opacity="0.7"/><stop offset="1" stop-color="' + color + '" stop-opacity="0"/></linearGradient></defs>' +
        '<path d="M0 10 H112" stroke="url(#' + g + 'l)" stroke-width="0.9" fill="none"/><path d="M208 10 H320" stroke="url(#' + g + 'r)" stroke-width="0.9" fill="none"/>' +
        '<g fill="none" stroke="' + color + '" stroke-width="0.9" stroke-opacity="0.8">' +
        '<ellipse cx="160" cy="10" rx="24" ry="6.2"/><ellipse cx="146" cy="10" rx="13" ry="4.4"/><ellipse cx="174" cy="10" rx="13" ry="4.4"/>' +
        '<path d="M112 10 C120 10 124 4 132 4 S144 10 150 10" /><path d="M208 10 C200 10 196 4 188 4 S176 10 170 10"/>' +
        '<path d="M112 10 C120 10 124 16 132 16 S144 10 150 10" stroke-opacity="0.45"/><path d="M208 10 C200 10 196 16 188 16 S176 10 170 10" stroke-opacity="0.45"/></g>' +
        '<rect x="157.5" y="7.5" width="5" height="5" transform="rotate(45 160 10)" fill="' + color + '"/>' +
        '<circle cx="132" cy="10" r="1.2" fill="' + color + '"/><circle cx="188" cy="10" r="1.2" fill="' + color + '"/></svg>';
    },
    /* lace-edge — the chapter break: a chain of loops across the full width, emerging from the margins */
    laceEdge: function (color) {
      var g = uid();
      return '<svg class="orn lace-edge" width="100%" height="18" aria-hidden="true"><defs>' +
        '<pattern id="' + g + 'p" width="36" height="18" patternUnits="userSpaceOnUse">' +
        '<path d="M0 9 C6 9 9 3 18 3 S30 9 36 9" fill="none" stroke="' + color + '" stroke-width="0.9" stroke-opacity="0.75"/>' +
        '<path d="M0 9 C6 9 9 15 18 15 S30 9 36 9" fill="none" stroke="' + color + '" stroke-width="0.9" stroke-opacity="0.4"/>' +
        '<circle cx="18" cy="9" r="1.2" fill="' + color + '"/><circle cx="0" cy="9" r="0.7" fill="' + color + '" fill-opacity="0.6"/></pattern>' +
        '<linearGradient id="' + g + 'f" x1="0" x2="1"><stop offset="0" stop-color="' + PAPER + '"/><stop offset="0.12" stop-color="' + PAPER + '" stop-opacity="0"/><stop offset="0.88" stop-color="' + PAPER + '" stop-opacity="0"/><stop offset="1" stop-color="' + PAPER + '"/></linearGradient></defs>' +
        '<rect width="100%" height="18" fill="url(#' + g + 'p)"/><rect width="100%" height="18" fill="url(#' + g + 'f)"/></svg>';
    },
    brush: function () { return '<svg class="orn brushline" viewBox="0 0 220 12" aria-hidden="true"><path d="M2 7 C55 1 110 11 218 4 C110 7 55 4 2 7 Z" fill="#1C1A17" fill-opacity="0.85"></path></svg>'; },
    nameline: function (color) { return '<svg width="72" height="10" viewBox="0 0 72 10" aria-hidden="true"><path d="M1 6 C20 1 40 9 71 4 C40 6 20 4 1 6 Z" fill="' + color + '"></path></svg>'; },
    branch: function (dot) { return '<svg class="orn branch" viewBox="0 0 170 18" aria-hidden="true"><path d="M0 12 C40 12 80 10 168 7" stroke="#1C1A17" stroke-width="1.2" fill="none" stroke-linecap="round"></path><path d="M86 10 C94 4 102 3 112 4" stroke="#1C1A17" stroke-width="1.2" fill="none" stroke-linecap="round"></path><circle cx="116" cy="4" r="2.4" fill="' + dot + '"></circle></svg>'; },
    enso: function (color) { return '<svg width="84" height="84" viewBox="0 0 88 88" aria-hidden="true"><path d="M72 24 A32 32 0 1 1 46 12" fill="none" stroke="' + color + '" stroke-width="3" stroke-linecap="round" stroke-opacity="0.4"></path></svg>'; },
    arc: function (color) { return '<svg class="arc" width="10" height="64" viewBox="0 0 10 64" aria-hidden="true"><path d="M8 2 C0 22 0 42 8 62" fill="none" stroke="' + color + '" stroke-width="2" stroke-linecap="round"></path></svg>'; },
    play: '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M5 3 L14 9 L5 15 Z" fill="#1C1A17"></path></svg>'
  };
  function seasonColor(s) { return getComputedStyle(document.documentElement).getPropertyValue('--' + s).trim() || '#4F6B4A'; }
  function arcColor(k) { return k === 'gold' ? '#B08D57' : seasonColor(k); }

  // Placeholder silhouette until real photos exist: category decides the stroke family, the season tints the crown.
  function silhouette(t, w, h) {
    var cat = (t.sp && t.sp.category) || 'other', col = seasonColor(t.season);
    var cx = w / 2, base = h * 0.95, top = h * 0.25;
    var body;
    if (cat === 'pine' || cat === 'conifer') {
      body = '<path d="M' + (cx + 4) + ' ' + base + ' C' + (cx) + ' ' + (h * 0.75) + ' ' + (cx - 20) + ' ' + (h * 0.65) + ' ' + (cx + 2) + ' ' + (h * 0.5) + ' C' + (cx + 12) + ' ' + (h * 0.4) + ' ' + (cx - 8) + ' ' + (h * 0.35) + ' ' + (cx + 6) + ' ' + top + '" stroke="#1C1A17" stroke-opacity="0.28" stroke-width="4" fill="none" stroke-linecap="round"></path>' +
        '<ellipse cx="' + (cx - w * 0.22) + '" cy="' + (h * 0.5) + '" rx="' + (w * 0.17) + '" ry="' + (h * 0.05) + '" fill="' + col + '" fill-opacity="0.14"></ellipse>' +
        '<ellipse cx="' + (cx + w * 0.22) + '" cy="' + (h * 0.37) + '" rx="' + (w * 0.19) + '" ry="' + (h * 0.055) + '" fill="' + col + '" fill-opacity="0.14"></ellipse>' +
        '<ellipse cx="' + cx + '" cy="' + (top) + '" rx="' + (w * 0.15) + '" ry="' + (h * 0.05) + '" fill="' + col + '" fill-opacity="0.14"></ellipse>';
    } else {
      body = '<g fill="none" stroke="#1C1A17" stroke-opacity="0.22" stroke-width="3" stroke-linecap="round"><path d="M' + cx + ' ' + base + ' L' + (cx - 2) + ' ' + (h * 0.62) + '"></path><path d="M' + (cx - 2) + ' ' + (h * 0.62) + ' C' + (cx - 20) + ' ' + (h * 0.55) + ' ' + (cx - 30) + ' ' + (h * 0.5) + ' ' + (cx - w * 0.2) + ' ' + (h * 0.44) + '"></path><path d="M' + (cx - 2) + ' ' + (h * 0.62) + ' C' + (cx + 10) + ' ' + (h * 0.52) + ' ' + (cx + 24) + ' ' + (h * 0.48) + ' ' + (cx + w * 0.2) + ' ' + (h * 0.42) + '"></path></g>' +
        '<ellipse cx="' + cx + '" cy="' + (h * 0.42) + '" rx="' + (w * 0.34) + '" ry="' + (h * 0.2) + '" fill="' + col + '" fill-opacity="0.11"></ellipse>';
    }
    return '<svg class="silhouette" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid slice" aria-hidden="true">' + body + '</svg>';
  }
  /* pick(t, shot, season): the photo of that shot in that season, else the same shot from any season (a real tree
     photographed outside its 見頃 still shows its face), else null. */
  function pick(t, shot, season) {
    var all = t.photos.filter(function (x) { return x.shot === shot; });
    return all.filter(function (x) { return !season || x.season === season; })[0] || (season ? all.filter(function (x) { return x.src; })[0] : null) || null;
  }
  function srcOf(p) { return p && p.src ? (/^https?:\/\//.test(p.src) ? p.src : BASE + p.src) : null; }
  function photo(t, shot, opts) {
    opts = opts || {};
    var p = pick(t, shot, opts.season), src = srcOf(p);
    var inner = src ? '<img src="' + esc(src) + '" alt="' + esc(opts.alt || '') + '" loading="lazy">' : silhouette(t, opts.w || 358, opts.h || 448);
    var cap = src ? '' : '<span class="cap">' + esc(opts.cap || ('写真 ' + shotLabel(shot) + (p ? ' · ' + SEASON[p.season].kanji : ''))) + '</span>';
    var slot = EDIT && t.sample ? '<span class="edit-slot" data-sample="' + esc(t.id) + '" data-shot="' + shot + '" data-season="' + esc((p && p.season) || opts.season || t.season) + '" hidden></span>' : '';
    return inner + cap + slot;
  }
  var SHOTS = { 1: '①正面', 2: '②正面横', 3: '③¾左', 4: '④¾右', 5: '⑤背面', 6: '⑥根元', 7: '⑦幹周', 8: '⑧枝ぶり', 9: '⑨状態', 10: '⑩比例' };
  function shotLabel(n) { return SHOTS[n] || ('' + n); }
  function sampleTag(t) { return t.sample ? '<span class="pill tag">示例</span>' : ''; }

  // ---- renderers ----
  function tradeCard(t, lang) {
    var k = TRADE[t.trade.status] || TRADE.unknown;
    return '<section class="export reveal">' + ORN.arc(arcColor(k.arc)) +
      '<span class="lbl">出口 · 輸出 · EXPORT</span>' +
      '<p class="zh">' + esc(k.zh) + '</p>' +
      '<p class="sub" lang="ja">' + esc(k.ja) + ' · <span class="en">' + esc(k.en) + '</span></p>' +
      '<p class="fixed">' + esc(k.sub) + '。' + FIXED_TRADE + ' <span class="num">最后核对 ' + esc(t.trade.verified_at || '—') + '</span></p></section>';
  }
  function tradeShort(t) { var k = TRADE[t.trade.status] || TRADE.unknown; return k.short ? '<span class="warn">' + esc(k.short) + '</span>' : ''; }
  function ageLine(t) { return t.measures.age_years_est ? '推定约 ' + t.measures.age_years_est + ' 年' : '树龄待记'; }

  function treeCard(t, lang) {
    var sp = t.sp || {};
    return '<a class="tcard reveal" href="' + treeHref(t) + '">' +
      '<div class="ph" style="aspect-ratio: 4 / 5">' + photo(t, 1, { w: 172, h: 214, season: t.season, cap: '②' }) + (t.sample ? '<span class="tl">' + sampleTag(t) + '</span>' : '') + '</div>' +
      '<span class="name">' + esc(speciesName(sp, 'zh')) + (name(t, 'zh') ? ' ·「' + esc(name(t, 'zh')) + '」' : '') + ' <span class="ja" lang="ja">' + esc(speciesName(sp, 'ja')) + '</span></span>' +
      '<span class="latin">' + esc(sp.latin || '') + '</span>' +
      '<span class="meta num">H ' + m(t.measures.height_cm) + ' · W ' + m(t.measures.width_cm) + ' · ' + esc(t.catalog_no) + '</span>' + tradeShort(t) + '</a>';
  }
  function signature(t, lang) {
    var sp = t.sp || {}, col = seasonColor(t.season), hero = pick(t, 1, t.season), tier = TIER[t.tier] || TIER.collection;
    var heroSeason = (hero && hero.season) || t.season;
    return '<a class="sig reveal s-' + t.season + '" href="' + treeHref(t) + '">' +
      '<div class="ph hero">' + photo(t, 1, { w: 358, h: 448, season: t.season, cap: '写真 ①正面 · ' + SEASON[t.season].kanji }) +
      '<div class="tl"><span class="pill season">' + SEASON[t.season].kanji + ' · 見頃</span>' + (hero && hero.taken_at ? '<span class="pill paper num" style="font-size:11px;letter-spacing:0">' + esc(hero.taken_at) + ' · ' + solarTerm(hero.taken_at) + (heroSeason !== t.season ? ' · ' + SEASON[heroSeason].kanji + '姿' : '') + '</span>' : '') + sampleTag(t) + '</div>' +
      '<span class="pill paper num bl" style="font-size:11px;letter-spacing:0.12em">' + esc(t.catalog_no) + '</span><span class="seal br">名木</span></div>' +
      '<div class="stack" style="gap:4px"><span class="tier">' + tier.zh + ' · ' + tier.en + '</span>' +
      '<h2>' + esc(name(t, 'zh') || speciesName(sp, 'zh')) + '</h2>' + ORN.nameline(col) +
      '<span class="dzh" style="font-size:17px">' + esc(speciesName(sp, 'zh')) + ' <span class="dja" lang="ja" style="font-size:13px;color:var(--muted)">' + esc(speciesName(sp, 'ja')) + '</span> <span class="latin" style="font-size:15px;color:var(--muted)">' + esc(sp.latin || '') + '</span></span>' +
      '<span class="num muted" style="font-size:13px">' + esc(t.form.zh || '') + (t.form.zh ? ' · ' : '') + 'H ' + m(t.measures.height_cm) + ' · W ' + m(t.measures.width_cm) + ' · ' + ageLine(t) + '</span>' +
      (sp.knowledge && sp.knowledge.zh && sp.knowledge.zh.intro ? '<span class="serif muted" style="font-size:13px;line-height:1.7">' + esc(sp.knowledge.zh.intro) + '</span>' : '') +
      (tradeShort(t) ? '<span class="muted" style="font-size:12px">' + (TRADE[t.trade.status] || TRADE.unknown).zh + '</span>' : '') + '</div></a>';
  }
  function rowItem(t, small) {
    var sp = t.sp || {};
    return '<a class="rowl' + (small ? ' small' : '') + ' reveal" href="' + treeHref(t) + '"><div class="ph">' + photo(t, 1, { w: 56, h: 56, cap: '' }) + '</div>' +
      '<div class="stack"><span class="' + (small ? '' : 'dzh') + '" style="font-size:' + (small ? 13 : 15) + 'px">' + esc(speciesName(sp, 'zh')) + (name(t, 'zh') ? ' ·「' + esc(name(t, 'zh')) + '」' : '') + ' <span class="ja" lang="ja" style="font-size:11px;color:var(--muted)">' + esc(speciesName(sp, 'ja')) + '</span>' + (t.sample ? ' <span class="muted" style="font-size:10px">示例</span>' : '') + '</span>' +
      (small ? '' : (tradeShort(t) ? '<span class="muted" style="font-size:11px">' + esc((TRADE[t.trade.status] || TRADE.unknown).short) + '</span>' : '<span class="latin" style="font-size:12px;color:var(--muted)">' + esc(sp.latin || '') + '</span>')) + '</div>' +
      '<span class="num muted" style="font-size:11px">H ' + m(t.measures.height_cm) + (small ? ' · W ' + m(t.measures.width_cm) : '') + ' · ' + esc(String(t.catalog_no).slice(-3)) + '</span></a>';
  }

  function chapterHead(s, current, date) {
    var S = SEASON[s], col = seasonColor(s);
    var line = s === current ? nextTermLine(date) : '見頃 ' + S.months;
    return '<div class="chapter-head s-' + s + '"><div class="kanji">' + ORN.enso(col) + '<span class="brush">' + S.kanji + '</span></div>' +
      '<div class="stack" style="gap:4px"><span class="title">' + S.sub.zh + '</span><span class="sub">' + S.sub.en + ' <span class="num" style="font-family:var(--f-sans)">· ' + esc(line) + '</span></span></div></div>';
  }

  function renderHome(root, data, lang) {
    var date = new Date(), current = seasonOf(date), order = seasonOrder(current);
    var published = data.trees.filter(function (t) { return t.status === 'published'; });
    if (Q.get('species')) return renderSpeciesPage(root, data, lang, Q.get('species'));
    if (Q.get('sold') === '1') return renderSold(root, data, lang);
    var html = '';
    html += '<nav class="season-nav" aria-label="四季">' + SEASONS.map(function (s) {
      return '<a href="#' + s + '" class="s-' + s + (s === current ? ' on' : '') + '">' + SEASON[s].kanji + '<small>' + (s === current ? '当季' : SEASON[s].months) + '</small></a>';
    }).join('') + '</nav>';
    order.forEach(function (s, idx) {
      var inSeason = sortTrees(published.filter(function (t) { return t.season === s && t.tier !== 'stock'; }));
      if (!inSeason.length) return;
      var full = idx < 2;  // the current season and the next get full chapters; later seasons are compact rows
      html += (idx ? '<div style="margin-top:26px">' + ORN.laceEdge(seasonColor(s)) + '</div>' : '') + '<section id="' + s + '" class="chapter s-' + s + '" style="margin-top:' + (idx ? 18 : 32) + 'px;display:flex;flex-direction:column;gap:16px">';
      if (full) {
        html += chapterHead(s, current, date);
        var real = inSeason.filter(function (t) { return t.real; });
        // the season opens on a REAL tree for sale whenever one exists; samples never take the hero slot then
        var heroes = real.length ? (real.filter(function (t) { return t.tier === 'signature'; })[0] ? real.filter(function (t) { return t.tier === 'signature'; }) : [real[0]])
                                 : inSeason.filter(function (t) { return t.tier === 'signature'; });
        heroes.forEach(function (t) { html += signature(t, lang); });
        var rest = inSeason.filter(function (t) { return heroes.indexOf(t) < 0; });
        if (rest.length) {
          html += '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:8px"><span class="lbl">' + TIER.collection.zh + ' · ' + TIER.collection.en + '</span><span class="muted" style="font-size:11px">' + SEASON[s].kanji + ' · ' + rest.length + ' 株</span></div>';
          html += '<div class="grid2">' + rest.map(function (t) { return treeCard(t, lang); }).join('') + '</div>';
        }
      } else {
        html += '<div style="display:flex;align-items:center;gap:14px"><span class="brush" style="font-size:44px;line-height:1;color:var(--season)">' + SEASON[s].kanji + '</span><div class="stack" style="gap:2px"><span class="dzh" style="font-size:15px">' + SEASON[s].sub.zh + '</span><span class="muted" style="font-size:11px">見頃 ' + SEASON[s].months + '</span></div></div>';
        html += '<div class="stack">' + inSeason.map(function (t) { return rowItem(t, false); }).join('') + '</div>';
      }
      html += '</section>';
    });
    var stock = sortTrees(published.filter(function (t) { return t.tier === 'stock'; }));
    if (stock.length) {
      html += '<div style="margin-top:36px">' + ORN.lace('#1C1A17') + '</div><section style="margin-top:16px;display:flex;flex-direction:column;gap:10px">' +
        '<div style="display:flex;justify-content:space-between;align-items:baseline"><span class="lbl">' + TIER.stock.zh + ' · ' + TIER.stock.en + '</span><span class="muted" style="font-size:11px">按树种 · ' + stock.length + ' 株</span></div>' +
        '<div class="stack">' + stock.map(function (t) { return rowItem(t, true); }).join('') + '</div></section>';
    }
    root.innerHTML = html;
    reveal(root);
  }

  function renderSpeciesPage(root, data, lang, sid) {
    var sp = data.species[sid];
    if (!sp) { root.innerHTML = '<p class="muted" style="padding:40px 0">未找到这个树种。<a href="' + BASE + '">回到展厅 →</a></p>'; return; }
    var list = sortTrees(data.trees.filter(function (t) { return t.species === sid && t.status === 'published'; }));
    var col = seasonColor(sp.best_season);
    document.title = shortZh(sp) + ' · 名木 Mei';
    root.innerHTML = '<section class="stack s-' + sp.best_season + '" style="gap:8px;padding-top:8px"><p style="font-size:13px"><a href="' + BASE + (EDIT ? '?edit=1' : '') + '">← 四季展厅</a></p>' +
      '<h1 class="dzh" style="font-size:30px;font-weight:400;line-height:1.3">' + esc(shortZh(sp)) + ' <span class="dja" lang="ja" style="font-size:16px;color:var(--muted)">' + esc(speciesName(sp, 'ja')) + '</span></h1>' +
      '<p class="latin" style="font-size:16px;color:var(--muted)">' + esc(sp.latin) + ' <span class="en" style="font-style:normal">· ' + esc(sp.en) + '</span></p>' +
      '<p class="muted" style="font-size:12px">見頃 <span style="color:var(--season)">' + SEASON[sp.best_season].kanji + '</span> · ' + SEASON[sp.best_season].months + ' · 在馆 ' + list.length + ' 株</p></section>' +
      '<div style="margin-top:18px">' + ORN.lace(col) + '</div>' +
      (list.length ? '<div class="grid2" style="margin-top:18px">' + list.map(function (t) { return treeCard(t, lang); }).join('') + '</div>' : '<p class="muted" style="margin-top:18px;font-size:14px">暂无在展之株。<a href="' + BASE + 'find/">委托我们寻找 →</a></p>') +
      knowledge(sp, true);
    reveal(root);
  }
  function renderSold(root, data, lang) {
    var list = sortTrees(data.trees.filter(function (t) { return t.status === 'sold' && t.show_when_sold !== false; }));
    document.title = '成交实绩 · 名木 Mei';
    root.innerHTML = '<section class="stack" style="gap:8px;padding-top:8px"><p style="font-size:13px"><a href="' + BASE + '">← 四季展厅</a></p><h1 class="dzh" style="font-size:30px;font-weight:400">成交实绩 <span class="dja" lang="ja" style="font-size:16px;color:var(--muted)">成約実績</span></h1></section>' +
      '<div style="margin-top:18px">' + ORN.lace('#1C1A17') + '</div>' +
      (list.length ? '<div class="stack" style="margin-top:12px">' + list.map(function (t) { return rowItem(t, false); }).join('') + '</div>' : '<p class="muted" style="margin-top:18px;font-size:14px">成交记录将在首批交付后公开。<a href="' + BASE + 'find/">委托我们寻木 →</a></p>');
    reveal(root);
  }

  function plaque(t, lang) {
    var sp = t.sp || {}, S = SEASON[t.season];
    var rows = [
      ['推定树龄', t.measures.age_years_est ? '<span class="num">约 ' + t.measures.age_years_est + ' 年<span style="font-size:11px;color:var(--muted)">（推定）</span></span>' : '<span class="muted">待记</span>'],
      ['树高', '<span class="num">' + m(t.measures.height_cm) + '</span>'],
      ['冠幅', '<span class="num">' + m(t.measures.width_cm) + '</span>'],
      ['干周（离地 1.2 m）', '<span class="num">' + (t.measures.trunk_girth_cm == null ? '—' : t.measures.trunk_girth_cm + ' cm') + '</span>'],
      ['根鉢', t.measures.root_ball_cm ? '<span class="num">' + t.measures.root_ball_cm + ' cm</span>' : '<span class="num muted">未起挖' + (t.logistics && t.logistics.root_ball_est_cm ? '（预计 约 ' + t.logistics.root_ball_est_cm + ' cm）' : '') + '</span>'],
      ['树形', t.form.zh ? esc(t.form.zh) + ' <span lang="ja" style="color:var(--muted);font-size:13px">' + esc(t.form.ja) + '</span>' : '<span class="muted">—</span>'],
      ['見頃', '<span style="color:var(--season)">' + S.kanji + '</span>' + (sp.best_season_note ? ' · ' + esc(sp.best_season_note) : '')],
      ['产地', '关东'],
      ['价格', '议价 <span lang="ja" style="color:var(--muted);font-size:13px">応談</span>'],
      ['整理番号', '<span class="num" style="letter-spacing:0.08em">' + esc(t.catalog_no) + '</span>']
    ];
    return '<dl class="plaque">' + rows.map(function (r) { return '<div class="row"><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>'; }).join('') + '</dl><p class="foot">尺寸为园方现场量测近似值，起挖与修剪后可能变化；树龄为推定。</p>';
  }
  function seasonsStrip(t) {
    return '<div class="grid4">' + SEASONS.map(function (s) {
      var p = t.photos.filter(function (x) { return x.shot === 1 && x.season === s; })[0];
      var best = s === t.season;
      var frame = p ? '<div class="ph" style="aspect-ratio:86/112;border-radius:10px;' + (best ? 'outline:1.5px solid var(--season);outline-offset:3px' : '') + '">' + photo(t, 1, { w: 86, h: 112, season: s, cap: '' }) + '</div>'
                    : '<div style="aspect-ratio:86/112;border:1px dashed var(--hairline);border-radius:10px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:10px;color:var(--muted);padding:8px;line-height:1.5">撮影予定</div>';
      return '<div class="stack s-' + s + '" style="gap:6px">' + frame + '<span class="brush" style="font-size:16px;color:var(--season)">' + SEASON[s].kanji + (best ? ' <span class="serif" style="font-size:10px">見頃</span>' : '') + '</span><span class="num muted" style="font-size:10px">' + (p && p.taken_at ? esc(p.taken_at.slice(5)) + ' · ' + solarTerm(p.taken_at) : '—') + '</span></div>';
    }).join('') + '</div>';
  }
  function gallery(t) {
    var shots = t.photos.filter(function (p) { return p.shot >= 2 && p.shot <= 10 && (t.sample ? p.shot >= 6 && p.season === t.season : true); });
    if (!shots.length) return '';
    return '<div class="grid2" style="gap:12px">' + shots.map(function (p) {
      return '<figure class="stack reveal" style="gap:6px"><div class="ph" style="aspect-ratio:175/148">' + photo(t, p.shot, { w: 175, h: 148, season: p.season, cap: shotLabel(p.shot) }) + '</div><figcaption class="muted" style="font-size:11px">' + esc(p.caption_zh || shotLabel(p.shot)) + (p.taken_at ? ' · ' + dateTerm(p.taken_at) : '') + '</figcaption></figure>';
    }).join('') + '</div>';
  }
  var LINKS = { baike: '百度百科', wiki_ja: 'Wikipedia（日本語）', wiki_en: 'Wikipedia（English）' };
  function knowledge(sp, onSpeciesPage) {
    var k = sp && sp.knowledge && sp.knowledge.zh; if (!k) return '';
    var rows = [['原产', k.origin], ['性格', k.character], ['文化', k.culture], ['生长', k.growth], ['养护', k.care]].filter(function (r) { return r[1]; });
    var links = Object.keys(sp.links || {}).filter(function (key) { return sp.links[key]; });
    return '<section class="panel knowledge reveal" style="margin-top:28px"><div style="display:flex;justify-content:space-between;align-items:baseline"><h2 class="dzh" style="font-size:19px;font-weight:400">树种小识 · ' + esc(shortZh(sp)) + '</h2><span lang="ja" class="muted" style="font-size:12px">樹種について</span></div>' +
      ORN.lace(seasonColor(sp.best_season)) +
      (k.intro ? '<p class="intro">' + esc(k.intro) + '</p>' : '') +
      '<dl>' + rows.map(function (r) { return '<div class="k"><dt>' + r[0] + '</dt><dd>' + esc(r[1]) + '</dd></div>'; }).join('') + '</dl>' +
      (links.length ? '<div class="links"><span class="lbl">延伸阅读</span>' + links.map(function (key) { return '<a href="' + esc(sp.links[key]) + '" target="_blank" rel="noopener noreferrer">' + LINKS[key] + ' ↗</a>'; }).join('') + '</div>' : '') +
      '<p class="muted" style="font-size:11px;line-height:1.6;margin-top:4px">一般知识，供参考；不构成对本株的承诺。' + (onSpeciesPage ? '' : '<a href="' + BASE + '?species=' + esc(sp.id) + EDITQ + '" style="margin-left:6px">本馆所有' + esc(shortZh(sp)) + ' →</a>') + '</p></section>';
  }
  function logisticsLine(t) {
    var L = t.logistics || {}, k = TRADE[t.trade.status] || TRADE.unknown;
    var bits = [k.zh.replace(/（.*$/, ''), L.nemawashi === 'done' ? '断根 已完成' + (L.nemawashi_at ? '（' + L.nemawashi_at + '）' : '') : L.nemawashi === 'in_progress' ? '断根 进行中' : '断根 未开始',
      L.root_ball_est_cm ? '根球 约 ' + L.root_ball_est_cm + ' cm' : null, L.est_weight_kg ? '估重 约 ' + (L.est_weight_kg / 1000).toFixed(1) + ' t' : null, L.crane_access === false ? '吊车受限' : L.crane_access === true ? '吊车可达' : null, L.earliest_ship ? '最早出货 ' + L.earliest_ship + '（休眠期）' : '出货窗口待定'].filter(Boolean);
    return '<section class="stack reveal" style="gap:8px;margin-top:24px"><span class="lbl">物流概要 · 輸送</span><p class="num" style="font-size:13px;line-height:1.8">' + bits.map(esc).join(' · ') + '</p><p style="font-size:13px"><a href="' + BASE + 'journey/">每一棵树的旅程 · 木の旅 →</a></p></section>';
  }
  function videoBlock(t) {
    if (!t.video) return '';
    if (t.video.src) return '<section style="margin-top:14px"><div class="ph" style="aspect-ratio:9/16;max-width:360px;margin:0 auto;background:#000"><video controls playsinline preload="metadata" src="' + esc(t.video.src) + '" style="position:absolute;inset:0;width:100%;height:100%;object-fit:contain"></video></div><p class="muted num" style="font-size:11px;text-align:center;margin-top:6px">環視' + (t.video.duration_s ? ' ' + t.video.duration_s + ' 秒' : '') + (t.video.taken_at ? ' · ' + esc(t.video.taken_at) : '') + '</p></section>';
    return '<section style="margin-top:14px"><div class="ph" style="aspect-ratio:358/219;display:flex;align-items:center;justify-content:center">' + silhouette(t, 358, 219) + '<button type="button" aria-label="播放视频" style="position:relative;width:56px;height:56px;border-radius:50%;border:1px solid var(--ink);background:rgba(246,242,234,0.9);display:flex;align-items:center;justify-content:center">' + ORN.play + '</button><span class="cap">環視 ' + (t.video.duration_s || '') + ' 秒 · 9:16 · ' + esc(t.video.taken_at || '') + '</span></div></section>';
  }

  function renderTree(root, data, lang) {
    var slug = Q.get('slug');
    var t = data.trees.filter(function (x) { return x.id === slug; })[0];
    if (!t) { root.innerHTML = '<p class="muted" style="padding:40px 0">未找到这株树。<a href="' + BASE + '">回到展厅 →</a></p>'; return; }
    var sp = t.sp || {}, col = seasonColor(t.season), hero = pick(t, 1, t.season), tier = TIER[t.tier] || TIER.collection;
    document.title = (name(t, 'zh') ? name(t, 'zh') + ' · ' : '') + speciesName(sp, 'zh') + ' · ' + t.catalog_no + ' · 名木 Mei';
    document.documentElement.className = 's-' + t.season;
    var left = '', right = '';
    left += '<div class="ph hero wide">' + photo(t, 1, { w: 358, h: 448, season: t.season, cap: '写真 ①正面 · 見頃の姿（' + SEASON[t.season].kanji + '）' }) +
      '<div class="tl"><span class="pill season">' + SEASON[t.season].kanji + ' · 見頃</span>' + (hero && hero.taken_at ? '<span class="pill paper num" style="font-size:11px;letter-spacing:0">' + esc(hero.taken_at) + ' · ' + solarTerm(hero.taken_at) + '</span>' : '') + sampleTag(t) + '</div>' +
      '<span class="pill paper num bl" style="font-size:11px;letter-spacing:0.12em">' + esc(t.catalog_no) + '</span><span class="seal br">名木</span></div>';
    left += '<section class="tree-name" style="padding-top:26px;display:grid;grid-template-columns:minmax(0,1fr) 36px;gap:12px"><div class="stack" style="gap:6px">' +
      '<span class="lbl" style="color:var(--gold-text)">' + tier.zh + ' · ' + tier.ja + ' · ' + tier.en + '</span>' +
      '<h1>' + esc(name(t, 'zh') || speciesName(sp, 'zh')) + '</h1>' + ORN.nameline(col) +
      '<p class="species">' + esc(sp.zh || '') + (t.cultivar ? ' ·「' + esc(t.cultivar) + '」' : '') + '</p><p class="latin">' + esc(sp.latin || '') + '</p><p class="en">' + esc(sp.en || '') + '</p></div>' +
      '<span class="vert" lang="ja">' + esc((name(t, 'ja') ? name(t, 'ja') + ' · ' : '') + speciesName(sp, 'ja')) + '</span></section>';
    if (sp.knowledge && sp.knowledge.zh && sp.knowledge.zh.intro) left += '<p class="serif muted reveal" style="font-size:14px;line-height:1.9;margin-top:14px">' + esc(sp.knowledge.zh.intro) + '</p>';
    if (t.text && t.text.zh && (t.text.zh.headline || t.text.zh.body)) {
      left += '<div style="margin-top:30px">' + ORN.brush() + '</div><section class="text stack reveal" style="gap:12px;margin-top:16px">' + (t.text.zh.headline ? '<h2>' + esc(t.text.zh.headline) + '</h2>' : '') + '<p>' + esc(t.text.zh.body) + '</p>' +
        (t.text.ja && t.text.ja.body ? '<details><summary lang="ja" style="font-size:13px;color:var(--accent);cursor:pointer">原文（日本語）を表示</summary><p lang="ja" style="margin-top:8px;font-size:15px;line-height:1.9">' + esc(t.text.ja.body) + '</p></details>' : '') + '</section>';
    }
    left += '<div style="margin-top:28px">' + ORN.lace(col) + '</div><section class="stack" style="gap:12px;margin-top:16px"><div style="display:flex;justify-content:space-between;align-items:baseline"><h2 class="dzh" style="font-size:20px;font-weight:400">四季 <span lang="ja" class="muted" style="font-size:13px">四季の姿</span></h2><span class="muted" style="font-size:11px">每张照片注明拍摄日与节气</span></div>' + seasonsStrip(t) + '</section>';
    var g = gallery(t); if (g) left += '<section style="margin-top:22px">' + g + '</section>';
    left += videoBlock(t);
    left += knowledge(sp);
    right += plaque(t, lang) + '<div style="margin-top:14px">' + tradeCard(t, lang) + '</div>' + logisticsLine(t) +
      '<p class="muted" style="font-size:11px;line-height:1.7;margin-top:18px">活体植物，存活不作保证。图像与尺寸为拍摄、量测当日之记录；出口整备（去土、修剪）会改变树姿。价格议定；出口可否与运输逐案确认。</p>' +
      '<div style="margin-top:24px">' + ORN.branch(col) + '</div>' +
      (t.status === 'sold' ? '<p class="muted" style="margin-top:14px;font-size:14px">此树已成交 · <a href="' + BASE + 'find/">委托我们寻找相近的一棵 →</a></p>'
        : t.status === 'reserved' ? '<p class="muted" style="margin-top:14px;font-size:14px">此树已有预约 · <a href="' + BASE + 'find/?ref=' + esc(t.catalog_no) + '">委托我们寻找相近的一棵 →</a></p>'
        : '<section class="stack" style="gap:12px;margin-top:14px"><a class="btn block" href="' + BASE + 'inquiry/?tree=' + esc(t.id) + '">询价 · お問い合わせ</a><p style="font-size:13px;text-align:center"><a href="' + BASE + 'find/?ref=' + esc(t.catalog_no) + '">想找与此相近的树？委托我们寻木 →</a></p></section>') +
      '<section style="padding-top:30px;display:flex;justify-content:space-between;align-items:flex-end"><div class="stack" style="gap:4px"><span class="dzh" style="font-size:15px">' + PROVENANCE.zh + '</span><span lang="ja" class="dja" style="font-size:12px;color:var(--muted)">' + PROVENANCE.ja + '</span><span class="en muted" style="font-size:12px">' + PROVENANCE.en + '</span><span class="num" style="font-size:12px;letter-spacing:0.12em;margin-top:8px">' + esc(t.catalog_no) + '</span></div><div id="qr" style="padding:6px;background:#fff;border-radius:10px;border:1px solid var(--hairline);width:76px;height:76px"></div></section>';
    root.innerHTML = '<div class="tree-grid"><div class="left">' + left + '</div><aside class="right">' + right + '</aside></div>';
    var qr = document.getElementById('qr'); if (qr && window.MeiQR) qr.innerHTML = window.MeiQR(location.href, 64);
    reveal(root);
  }

  function reveal(root) {
    var els = root.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) { els.forEach(function (e) { e.classList.add('in'); }); return; }
    var io = new IntersectionObserver(function (entries) { entries.forEach(function (en, i) { if (en.isIntersecting) { setTimeout(function () { en.target.classList.add('in'); }, Math.min(i * 80, 240)); io.unobserve(en.target); } }); }, { rootMargin: '0px 0px -10% 0px' });
    els.forEach(function (e) { io.observe(e); });
  }
  function loadScript(src) { return new Promise(function (res, rej) { var s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = function () { rej(new Error(src)); }; document.head.appendChild(s); }); }

  function boot() {
    var lang = getLang();
    var home = document.getElementById('mei-home'), tree = document.getElementById('mei-tree');
    document.querySelectorAll('[data-season-now]').forEach(function (el) { el.textContent = nextTermLine(new Date()); });
    loadData().then(function (data) {
      var banner = document.getElementById('sample-banner');
      if (banner && data.trees.some(function (t) { return t.sample; })) banner.textContent = data.hasReal ? '标「示例」者为样本，正陆续替换为实拍与在售之木' : '样本预览 · サンプル · 照片为占位，树木数据为示例';
      if (home) renderHome(home, data, lang);
      if (tree) renderTree(tree, data, lang);
      if (EDIT) loadScript(BASE + 'assets/auth.js').then(function () { return loadScript(BASE + 'assets/edit.js'); }).catch(function () { if (banner) banner.textContent = '编辑模式加载失败'; });
    }).catch(function (e) { (home || tree || document.body).insertAdjacentHTML('beforeend', '<p class="muted">数据加载失败：' + esc(e.message) + '</p>'); });
  }
  window.Mei = { solarTerm: solarTerm, seasonOf: seasonOf, seasonOrder: seasonOrder, sortTrees: sortTrees, TRADE: TRADE, SEASON: SEASON, ORN: ORN, BASE: BASE };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
