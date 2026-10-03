/* desk.js — 审: the staff/admin desk (Chinese UI). v0: review queue · the supplier's record (read-only) · media
 * previews on signed URLs · Chinese/English label text · tier + names · the publish gate · publish (admin) ·
 * send back to the supplier with a note · reserved/sold/withdrawn/re-list · pending species approval (admin).
 * Every call goes through MeiAuth.api with a fresh token; the server decides what each role may do.
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var STATUS = { draft: '下书き', review: '审查中', published: '已公开', reserved: '预约中', sold: '已成交', withdrawn: '已下架' };
  var FILTERS = [['review', '审查中'], ['draft', '下书き'], ['published', '已公开'], ['reserved', '预约'], ['sold', '成交'], ['withdrawn', '下架'], ['all', '全部']];
  var SEASONS = [['spring', '春'], ['summer', '夏'], ['autumn', '秋'], ['winter', '冬']];
  var TIERS = [['signature', '铭品 signature'], ['collection', '名木 collection'], ['stock', '庭木 stock']];
  var CATS = ['pine', 'conifer', 'maple', 'flowering', 'evergreen', 'deciduous', 'other'];
  var SHOTS = ['①正面', '②正面横', '③¾左', '④¾右', '⑤背面', '⑥根元', '⑦干周', '⑧枝条', '⑨状态', '⑩比例'];
  var FORMS = { chokkan: '直干', kyokkan: '曲干', shakan: '斜干', sokan: '双干', kabudachi: '丛生多干', monkaburi: '门冠型', shidare: '垂枝', tamachirashi: '玉散', danzukuri: '层云', shizen: '自然树形' };
  var state = { me: null, filter: 'review', trees: [], totals: {}, tree: null, media: [], texts: [], gate: null, pending: [] };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function isAdmin() { return state.me && state.me.member.role === 'admin'; }
  function msg(id, text, err) { var m = $(id); if (!m) return; m.textContent = text || ''; m.className = 'msg' + (err ? ' err' : ''); }
  function fmt(iso) { return iso ? String(iso).slice(0, 16).replace('T', ' ') : '—'; }

  // ---- queue ----
  function renderFilters() {
    $('filters').innerHTML = FILTERS.map(function (f) { var n = f[0] === 'all' ? Object.keys(state.totals).reduce(function (a, k) { return a + state.totals[k]; }, 0) : (state.totals[f[0]] || 0); return '<button type="button" class="chip' + (state.filter === f[0] ? ' on' : '') + '" data-v="' + f[0] + '">' + f[1] + (n ? ' <span class="num">' + n + '</span>' : '') + '</button>'; }).join('');
    $('filters').querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { state.filter = b.dataset.v; loadQueue(); }); });
  }
  function renderQueue() {
    var el = $('queue');
    if (!state.trees.length) { el.innerHTML = '<p class="muted" style="font-size:13px;padding-top:8px">此栏暂无树木。</p>'; return; }
    el.innerHTML = state.trees.map(function (t) {
      return '<button type="button" class="row' + (state.tree && state.tree.id === t.id ? ' on' : '') + '" data-id="' + t.id + '"><span><span class="num muted" style="font-size:11px;letter-spacing:0.08em">' + esc(t.catalog_no) + '</span> <span class="status ' + esc(t.status) + '">' + esc(STATUS[t.status] || t.status) + '</span><br>' +
        esc(t.species_zh || t.species_ja) + (t.given_name_zh || t.given_name_ja ? ' ·「' + esc(t.given_name_zh || t.given_name_ja) + '」' : '') + (t.species_status && t.species_status !== 'approved' ? ' <span class="muted" style="font-size:11px">（树种待审）</span>' : '') +
        '<br><span class="muted" style="font-size:11px">' + esc(t.garden || '—') + ' · 照片 ' + t.photos + (t.videos ? ' · 视频 ' + t.videos : '') + ' · ' + fmt(t.updated_at) + '</span></span></button>';
    }).join('');
    el.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { openTree(b.dataset.id); }); });
  }
  function loadQueue() {
    renderFilters();
    return MeiAuth.api('queue', { query: { status: state.filter } }).then(function (r) {
      if (r.status >= 300) { $('queue').innerHTML = '<p class="msg err">' + esc(r.data.error || '加载失败') + '</p>'; return; }
      state.trees = r.data.trees || []; state.totals = r.data.totals || {};
      $('totals').textContent = Object.keys(state.totals).map(function (k) { return (STATUS[k] || k) + ' ' + state.totals[k]; }).join(' · ');
      renderFilters(); renderQueue();
    });
  }

  // ---- detail ----
  function openTree(id) {
    $('detail').innerHTML = '<p class="muted" style="padding-top:10px">读取中…</p>';
    return Promise.all([MeiAuth.api('tree_get', { query: { id: id } }), MeiAuth.api('media_urls', { query: { id: id } }), MeiAuth.api('publish_check', { query: { id: id } })]).then(function (res) {
      if (res[0].status >= 300) { $('detail').innerHTML = '<p class="msg err">' + esc(res[0].data.error || '读取失败') + '</p>'; return; }
      state.tree = res[0].data.tree; state.texts = res[0].data.texts || []; state.garden = res[0].data.garden; state.sendback = res[0].data.sendback;
      state.media = (res[1].data && res[1].data.media) || []; state.gate = res[2].data;
      renderQueue(); renderDetail();
    });
  }
  function latest(lang) { return state.texts.filter(function (x) { return x.lang === lang; })[0] || {}; }
  function renderDetail() {
    var t = state.tree, sp = t.species_id, zh = latest('zh'), en = latest('en');
    var photos = state.media.filter(function (m) { return m.kind === 'photo'; }), videos = state.media.filter(function (m) { return m.kind === 'video'; });
    var html = '';
    html += '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;padding-top:6px"><h2 class="dzh" style="font-size:22px;font-weight:400">' + esc(t.catalog_no) + ' <span class="status ' + esc(t.status) + '">' + esc(STATUS[t.status] || t.status) + '</span></h2>' +
      '<span class="muted" style="font-size:12px">' + esc(state.garden ? state.garden.name_ja : '') + (t.plot_ref ? ' · ' + esc(t.plot_ref) : '') + ' · 提交 ' + fmt(t.submitted_at) + (t.published_at ? ' · 公开 ' + fmt(t.published_at) : '') + '</span></div>';
    if (state.sendback) html += '<p class="msg" style="font-size:13px">上次退回备注：' + esc(state.sendback) + '</p>';
    // media
    html += '<div class="sec"><h3>照片与视频 <span>' + photos.length + ' 张 · ' + videos.length + ' 段 · 预览链接 1 小时有效</span></h3><div class="thumbs">' +
      photos.map(function (m) { return '<figure><a href="' + esc(m.url || '#') + '" target="_blank" rel="noopener"><img src="' + esc(m.url || '') + '" alt="" loading="lazy"></a><figcaption>' + esc(SHOTS[(m.shot_no || 0) - 1] || ('#' + m.shot_no)) + (m.season ? ' · ' + esc({ spring: '春', summer: '夏', autumn: '秋', winter: '冬' }[m.season]) : '') + '</figcaption></figure>'; }).join('') +
      videos.map(function (m) { return '<figure><video src="' + esc(m.url || '') + '" preload="metadata" muted playsinline controls></video><figcaption>视频' + (m.duration_s ? ' ' + m.duration_s + 's' : '') + '</figcaption></figure>'; }).join('') + '</div></div>';
    // the supplier's record
    html += '<div class="sec"><h3>园主记录 <span>原文，只读</span></h3><div class="kv">' +
      [['树种', sp], ['名（日）', t.given_name_ja], ['品种（日）', t.cultivar_ja], ['树高', t.height_cm && t.height_cm + ' cm'], ['冠幅', t.width_cm && t.width_cm + ' cm'], ['干周', t.trunk_girth_cm && t.trunk_girth_cm + ' cm'], ['根鉢', t.root_ball_cm && t.root_ball_cm + ' cm'], ['树龄（推定）', t.age_years_est && t.age_years_est + ' 年'],
       ['树形', FORMS[t.form_id] || t.form_id], ['見頃', t.best_season_override], ['断根', t.nemawashi_status], ['断根日', (t.nemawashi_dates || []).join(', ')]].map(function (r) { return '<div><b>' + r[0] + '</b>' + esc(r[1] || '—') + '</div>'; }).join('') + '</div>' +
      (t.supplier_notes_ja ? '<div class="ro" lang="ja">' + esc(t.supplier_notes_ja) + '</div>' : '<p class="muted" style="font-size:12px">（无备注）</p>') + '</div>';
    // text
    html += '<div class="sec"><h3>中文文案 <span>人工定稿；每次保存为新版本，公开页取最新</span></h3>' +
      '<input id="t-head" class="inp" placeholder="标题一句（如：三十年前自山野移入，六干并立）" maxlength="200" value="' + esc(zh.headline || '') + '">' +
      '<textarea id="t-body" class="inp" rows="6" maxlength="4000" placeholder="正文：姿态、来历、季相、养护记录。不写价格、不承诺出口与存活。">' + esc(zh.body || '') + '</textarea>' +
      '<details><summary class="muted" style="font-size:12px;cursor:pointer">English（可选）</summary><input id="t-head-en" class="inp" style="margin-top:8px" placeholder="Headline" maxlength="200" value="' + esc(en.headline || '') + '"><textarea id="t-body-en" class="inp" rows="4" maxlength="4000" style="margin-top:8px" placeholder="Body">' + esc(en.body || '') + '</textarea></details>' +
      '<div style="display:flex;gap:8px;align-items:center"><button type="button" id="t-save" class="btn small ghost">保存文案</button><span id="t-msg" class="msg"></span></div></div>';
    // attributes
    html += '<div class="sec"><h3>展示属性</h3><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px">' +
      '<label class="stack" style="gap:4px"><span class="lb">等级</span><select id="a-tier" class="inp">' + TIERS.map(function (x) { return '<option value="' + x[0] + '"' + (t.tier === x[0] ? ' selected' : '') + '>' + x[1] + '</option>'; }).join('') + '</select></label>' +
      '<label class="stack" style="gap:4px"><span class="lb">名（中）</span><input id="a-zh" class="inp" maxlength="80" value="' + esc(t.given_name_zh || '') + '"></label>' +
      '<label class="stack" style="gap:4px"><span class="lb">Name (EN)</span><input id="a-en" class="inp" maxlength="80" value="' + esc(t.given_name_en || '') + '"></label>' +
      '<label class="stack" style="gap:4px"><span class="lb">品种（中）</span><input id="a-cv" class="inp" maxlength="80" value="' + esc(t.cultivar_zh || '') + '"></label>' +
      '<label class="stack" style="gap:4px"><span class="lb">見頃（覆盖树种默认）</span><select id="a-season" class="inp"><option value="">— 树种默认 —</option>' + SEASONS.map(function (x) { return '<option value="' + x[0] + '"' + (t.best_season_override === x[0] ? ' selected' : '') + '>' + x[1] + '</option>'; }).join('') + '</select></label>' +
      '<label class="stack" style="gap:4px"><span class="lb">排序权重（大者在前）</span><input id="a-sort" class="inp num" type="number" min="-1000" max="1000" value="' + esc(t.sort_weight == null ? 0 : t.sort_weight) + '"></label>' +
      '<label class="stack" style="gap:4px"><span class="lb">最早出货窗口</span><input id="a-ship" class="inp" maxlength="80" placeholder="2026-12" value="' + esc(t.earliest_ship_window || '') + '"></label></div>' +
      '<div style="display:flex;gap:8px;align-items:center"><button type="button" id="a-save" class="btn small ghost">保存属性</button><span id="a-msg" class="msg"></span></div></div>';
    // gate + actions
    var g = state.gate || { items: [], ready: false };
    html += '<div class="sec"><h3>发布门 <span>' + (g.ready ? '可以发布' : '尚未齐备') + '</span></h3><div class="gate-list">' + g.items.map(function (i) { return '<span class="' + (i.ok ? 'ok' : 'no') + (i.required ? '' : ' opt') + '">' + esc(i.zh) + (i.required ? '' : '（建议）') + '</span>'; }).join('') + '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding-top:6px">' +
      (t.status === 'review' || t.status === 'draft' || t.status === 'withdrawn' ? '<button type="button" id="g-publish" class="btn small"' + (isAdmin() && g.ready ? '' : ' disabled') + ' title="' + (isAdmin() ? '' : '仅管理员可发布') + '">发布到展厅</button>' : '') +
      (t.status === 'review' || t.status === 'draft' ? '<button type="button" id="g-back" class="btn small danger">退回园主…</button>' : '') +
      (t.status === 'published' ? '<button type="button" class="btn small ghost" data-set="reserved">标记预约</button><button type="button" class="btn small ghost" data-set="sold">标记成交</button>' : '') +
      (t.status === 'reserved' ? '<button type="button" class="btn small ghost" data-set="published">取消预约</button><button type="button" class="btn small ghost" data-set="sold">标记成交</button>' : '') +
      (t.status === 'sold' ? '<button type="button" class="btn small ghost" data-set="published">重新上架</button>' : '') +
      (t.status === 'published' || t.status === 'reserved' ? '<button type="button" class="btn small danger" data-set="withdrawn"' + (isAdmin() ? '' : ' disabled') + '>下架</button>' : '') +
      (t.status === 'withdrawn' && t.published_at ? '<button type="button" class="btn small ghost" data-set="published"' + (isAdmin() ? '' : ' disabled') + '>重新上架</button>' : '') +
      '<span id="g-msg" class="msg"></span></div>' +
      '<div id="g-backbox" class="stack" style="gap:8px" hidden><textarea id="g-note" class="inp" rows="3" maxlength="1000" placeholder="给园主的话（日文更好）：例 ⑥根元の写真をお願いします。"></textarea><div style="display:flex;gap:8px"><button type="button" id="g-back-go" class="btn small danger">确认退回</button><button type="button" id="g-back-no" class="btn small ghost">取消</button></div></div></div>';
    html += '<p class="muted" style="font-size:12px;padding-top:12px">公开后的页面：<a href="../t/?slug=' + esc(t.slug) + '" target="_blank" rel="noopener">../t/' + esc(t.slug) + '</a>（发布后最多 5 分钟更新）</p>';
    $('detail').innerHTML = html;
    bindDetail();
  }
  function bindDetail() {
    var t = state.tree;
    $('t-save').addEventListener('click', function () {
      var zhBody = { id: t.id, lang: 'zh', headline: $('t-head').value, body: $('t-body').value };
      msg('t-msg', '保存中…');
      MeiAuth.api('tree_text_save', { body: zhBody }).then(function (r) {
        if (r.status >= 300) throw new Error(r.data.error || '保存失败');
        var enH = $('t-head-en').value.trim(), enB = $('t-body-en').value.trim();
        return enH || enB ? MeiAuth.api('tree_text_save', { body: { id: t.id, lang: 'en', headline: enH, body: enB } }) : { status: 200 };
      }).then(function (r) { if (r.status >= 300) throw new Error(r.data.error || 'EN 保存失败'); msg('t-msg', '已保存。'); return refreshGate(); }).catch(function (e) { msg('t-msg', e.message, true); });
    });
    $('a-save').addEventListener('click', function () {
      var body = { id: t.id, tier: $('a-tier').value, given_name_zh: $('a-zh').value, given_name_en: $('a-en').value, cultivar_zh: $('a-cv').value, best_season_override: $('a-season').value || null, sort_weight: $('a-sort').value || 0, earliest_ship_window: $('a-ship').value };
      msg('a-msg', '保存中…');
      MeiAuth.api('tree_set', { body: body }).then(function (r) { if (r.status >= 300) throw new Error(r.data.error || '保存失败'); state.tree = r.data.tree; msg('a-msg', '已保存。'); return refreshGate(); }).catch(function (e) { msg('a-msg', e.message, true); });
    });
    var pub = $('g-publish'); if (pub) pub.addEventListener('click', function () {
      if (!confirm('发布 ' + t.catalog_no + ' 到展厅？照片将复制到公开存储。')) return;
      msg('g-msg', '发布中…');
      MeiAuth.api('tree_publish', { body: { id: t.id } }).then(function (r) {
        if (r.status >= 300) throw new Error(r.data.error || '发布失败');
        msg('g-msg', '已发布 · 复制 ' + r.data.copied.length + ' 个媒体' + (r.data.skipped.length ? ' · 跳过 ' + r.data.skipped.length + '（格式不可公开）' : ''));
        return loadQueue().then(function () { return openTree(t.id); });
      }).catch(function (e) { msg('g-msg', e.message, true); });
    });
    var back = $('g-back'); if (back) back.addEventListener('click', function () { $('g-backbox').hidden = false; $('g-note').focus(); });
    var no = $('g-back-no'); if (no) no.addEventListener('click', function () { $('g-backbox').hidden = true; });
    var go = $('g-back-go'); if (go) go.addEventListener('click', function () {
      msg('g-msg', '退回中…');
      MeiAuth.api('tree_sendback', { body: { id: t.id, note: $('g-note').value } }).then(function (r) { if (r.status >= 300) throw new Error(r.data.error || '退回失败'); return loadQueue().then(function () { return openTree(t.id); }); }).catch(function (e) { msg('g-msg', e.message, true); });
    });
    $('detail').querySelectorAll('[data-set]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (b.dataset.set === 'withdrawn' && !confirm('下架 ' + t.catalog_no + '？展厅将不再显示。')) return;
        msg('g-msg', '更新中…');
        MeiAuth.api('tree_set', { body: { id: t.id, status: b.dataset.set } }).then(function (r) { if (r.status >= 300) throw new Error(r.data.error || '更新失败'); return loadQueue().then(function () { return openTree(t.id); }); }).catch(function (e) { msg('g-msg', e.message, true); });
      });
    });
  }
  function refreshGate() {
    return MeiAuth.api('publish_check', { query: { id: state.tree.id } }).then(function (r) { if (r.status < 300) { state.gate = r.data; var g = $('g-publish'); if (g) g.disabled = !(isAdmin() && r.data.ready); var list = $('detail').querySelector('.gate-list'); if (list) list.innerHTML = r.data.items.map(function (i) { return '<span class="' + (i.ok ? 'ok' : 'no') + (i.required ? '' : ' opt') + '">' + esc(i.zh) + (i.required ? '' : '（建议）') + '</span>'; }).join(''); } });
  }

  // ---- pending species ----
  function renderPending() {
    var el = $('pending'); $('pend-count').textContent = state.pending.length ? state.pending.length + ' 种' : '';
    if (!state.pending.length) { el.innerHTML = '<p class="muted" style="font-size:12px">无待审树种。</p>'; return; }
    el.innerHTML = state.pending.map(function (s) {
      return '<form class="pending" data-id="' + esc(s.id) + '"><div><span class="dja" lang="ja" style="font-size:16px">' + esc(s.ja_kanji) + '</span> <span class="muted" style="font-size:12px">' + esc(s.ja_reading || '') + ' · ' + fmt(s.created_at) + '</span></div>' +
        '<div class="grid"><input name="zh_hans" class="inp" placeholder="中文名（人工，不按汉字映射）" required maxlength="60"><input name="latin" class="inp" placeholder="学名 Genus species" required maxlength="80"><input name="en" class="inp" placeholder="English" maxlength="120">' +
        '<select name="category" class="inp">' + CATS.map(function (c) { return '<option' + (c === 'other' ? ' selected' : '') + '>' + c + '</option>'; }).join('') + '</select>' +
        '<select name="best_season" class="inp">' + SEASONS.map(function (x) { return '<option value="' + x[0] + '"' + (x[0] === 'summer' ? ' selected' : '') + '>見頃 ' + x[1] + '</option>'; }).join('') + '</select><input name="rank" class="inp num" type="number" min="1" max="999" value="50" placeholder="rank"></div>' +
        '<div style="display:flex;gap:8px;align-items:center"><button type="submit" class="btn small"' + (isAdmin() ? '' : ' disabled title="仅管理员可审定"') + '>审定</button><span class="msg"></span></div></form>';
    }).join('');
    el.querySelectorAll('form').forEach(function (f) {
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        var body = { id: f.dataset.id }; ['zh_hans', 'latin', 'en', 'category', 'best_season', 'rank'].forEach(function (k) { body[k] = f.elements[k].value.trim(); });
        var m = f.querySelector('.msg'); m.textContent = '审定中…'; m.className = 'msg';
        MeiAuth.api('species_approve', { body: body }).then(function (r) { if (r.status >= 300) throw new Error(r.data.error || '审定失败'); return loadPending(); }).catch(function (ex) { m.textContent = ex.message; m.className = 'msg err'; });
      });
    });
  }
  function loadPending() { return MeiAuth.api('species_pending').then(function (r) { state.pending = (r.data && r.data.species) || []; renderPending(); }); }

  // ---- boot ----
  $('logout').addEventListener('click', function (e) { e.preventDefault(); MeiAuth.logout().then(function () { location.reload(); }); });
  MeiAuth.requireLogin($('gate'), { title: '审 · 工作台登录', hint: 'スタッフ・管理者のみ。' }).then(function () { return MeiAuth.api('me'); }).then(function (r) {
    if (r.status === 403) { $('gate').innerHTML = '<p class="muted">此账号不是成员。请联系管理员。</p>'; return; }
    if (r.status === 503) { $('gate').innerHTML = '<p class="muted">数据库未连接（环境变量）。</p>'; return; }
    if (r.status >= 300) { $('gate').innerHTML = '<p class="muted">' + esc(r.data.error || '错误') + '</p>'; return; }
    if (r.data.member.role === 'supplier') { $('gate').innerHTML = '<p class="muted">工作台仅限工作人员。供给者请前往 <a href="../in/">入 · 供給者ページ →</a></p>'; return; }
    state.me = r.data; $('who').textContent = (r.data.member.name || r.data.user.email) + ' · ' + r.data.member.role;
    $('gate').hidden = true; $('app').hidden = false;
    return Promise.all([loadQueue(), loadPending()]);
  }).catch(function (e) { $('gate').innerHTML = '<p class="muted">' + esc(e.message) + '</p>'; });
})();
