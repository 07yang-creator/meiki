/* intake.js — 入: the supplier's page. Japanese UI, phone-first.
 * Flow: gate in place → me → species pick-list (registry; 「その他」 proposes a pending species) → own trees →
 * form → 下書き保存 (tree_save) → photos/video straight to Storage (media_sign → PUT → media_commit) → 提出.
 * Photos are re-encoded in the browser to ≤2000 px JPEG, which also strips EXIF/GPS before anything leaves the phone.
 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var SEASONS = [['spring', '春'], ['summer', '夏'], ['autumn', '秋'], ['winter', '冬']];
  var FORMS = [['chokkan', '直幹'], ['kyokkan', '曲幹（模様木）'], ['shakan', '斜幹'], ['sokan', '双幹'], ['kabudachi', '株立ち'], ['monkaburi', '門かぶり'], ['shidare', '枝垂れ'], ['tamachirashi', '玉散らし'], ['danzukuri', '段作り'], ['shizen', '自然樹形']];
  var SHOTS = ['①正面', '②正面横', '③¾左', '④¾右', '⑤後ろ', '⑥根元', '⑦幹周', '⑧枝ぶり', '⑨状態', '⑩比較'];
  var NEMA = [['not_started', '未'], ['in_progress', '進行中'], ['done', '済']];
  var STATUS_JA = { draft: '下書き', review: '審査中', published: '公開中', reserved: '予約', sold: '成約', withdrawn: '取下げ' };
  var state = { me: null, species: [], trees: [], tree: null, media: [], form: null, season: null, nema: null, shootSeason: null };

  function msg(text, err) { var m = $('msg'); m.textContent = text || ''; m.className = 'msg' + (err ? ' err' : ''); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function today() { var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function speciesById(id) { return state.species.filter(function (s) { return s.id === id; })[0]; }
  function seasonOfMonth(m) { return m >= 3 && m <= 5 ? 'spring' : m >= 6 && m <= 8 ? 'summer' : m >= 9 && m <= 11 ? 'autumn' : 'winter'; }

  // ---- chips ----
  function chips(el, items, current, onPick, cls) {
    el.innerHTML = items.map(function (it) { return '<button type="button" class="chip ' + (cls || '') + ' s-' + it[0] + (current === it[0] ? ' on' : '') + '" data-v="' + it[0] + '">' + esc(it[1]) + '</button>'; }).join('');
    el.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { onPick(b.dataset.v); }); });
  }
  function renderChips() {
    chips($('f-form'), FORMS, state.form, function (v) { state.form = state.form === v ? null : v; renderChips(); });
    var sp = speciesById($('f-species').value);
    var dflt = sp ? sp.best_season : null;
    chips($('f-season'), SEASONS, state.season || dflt, function (v) { state.season = v; renderChips(); }, 'season');
    chips($('f-nema'), NEMA, state.nema, function (v) { state.nema = v; renderChips(); });
    $('f-nema-date').style.display = state.nema && state.nema !== 'not_started' ? '' : 'none';
    chips($('shoot-season'), SEASONS, state.shootSeason || seasonOfMonth(new Date().getMonth() + 1), function (v) { state.shootSeason = v; renderChips(); }, 'season');
  }

  // ---- species ----
  function renderSpecies() {
    var sel = $('f-species');
    var approved = state.species.filter(function (s) { return s.status === 'approved'; });
    var pending = state.species.filter(function (s) { return s.status !== 'approved'; });
    sel.innerHTML = '<option value="">— 樹種を選ぶ —</option>' +
      approved.map(function (s) { return '<option value="' + esc(s.id) + '">' + esc(s.ja_kanji) + (s.ja_reading ? '（' + esc(s.ja_reading.split(' ')[0]) + '）' : '') + (s.zh_hans ? ' — ' + esc(s.zh_hans) : '') + '</option>'; }).join('') +
      (pending.length ? '<optgroup label="確認待ち（スタッフが中文名・学名を付けます）">' + pending.map(function (s) { return '<option value="' + esc(s.id) + '">' + esc(s.ja_kanji) + '</option>'; }).join('') + '</optgroup>' : '') +
      '<option value="__other__">その他…（新しい樹種を提案）</option>';
    if (state.tree && state.tree.species_id) sel.value = state.tree.species_id;
  }
  $('f-species').addEventListener('change', function () {
    if (this.value === '__other__') {
      var ja = prompt('樹種名（漢字 · 例: 木斛）'); if (!ja) { this.value = (state.tree && state.tree.species_id) || ''; return; }
      var reading = prompt('読み（カナ · 任意）') || '';
      var sel = this;
      MeiAuth.api('species_propose', { body: { ja_kanji: ja.trim(), ja_reading: reading.trim() } }).then(function (r) {
        if (r.status >= 300) { msg(r.data.error || '提案できませんでした', true); sel.value = ''; return; }
        if (!speciesById(r.data.species.id)) state.species.push(r.data.species);
        renderSpecies(); sel.value = r.data.species.id; state.season = null; renderChips();
        msg(r.data.existing ? 'この樹種はすでにあります。' : '提案しました。スタッフが確認するまで「確認待ち」のまま使えます（公開は確認後）。');
      });
      return;
    }
    state.season = null; renderChips();
  });

  // ---- trees list ----
  function renderTrees() {
    var el = $('trees');
    if (!state.trees.length) { el.innerHTML = '<p class="muted" style="font-size:13px">まだ樹木がありません。「＋ 新しい樹木」から。</p>'; return; }
    el.innerHTML = state.trees.map(function (t) {
      var sp = speciesById(t.species_id);
      return '<a href="#" data-id="' + t.id + '"><span><span class="num muted" style="font-size:11px;letter-spacing:0.08em">' + esc(t.catalog_no) + '</span><br>' + esc(sp ? sp.ja_kanji : t.species_id) + (t.given_name_ja ? ' ·「' + esc(t.given_name_ja) + '」' : '') + '</span><span class="status ' + esc(t.status) + '">' + esc(STATUS_JA[t.status] || t.status) + '</span></a>';
    }).join('');
    el.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); openTree(a.dataset.id); }); });
  }
  function loadTrees() { return MeiAuth.api('my_trees').then(function (r) { state.trees = (r.data && r.data.trees) || []; renderTrees(); }); }

  // ---- form ----
  function fillForm(t) {
    state.tree = t; state.media = [];
    $('f-title').textContent = t ? (t.given_name_ja || '樹木') : '新しい樹木';
    $('f-no').textContent = t ? t.catalog_no : '整理番号は保存時に付きます';
    renderSpecies();
    $('f-name').value = (t && t.given_name_ja) || ''; $('f-cultivar').value = (t && t.cultivar_ja) || '';
    $('f-h').value = t && t.height_cm != null ? t.height_cm : ''; $('f-w').value = t && t.width_cm != null ? t.width_cm : '';
    $('f-g').value = t && t.trunk_girth_cm != null ? t.trunk_girth_cm : ''; $('f-r').value = t && t.root_ball_cm != null ? t.root_ball_cm : '';
    $('f-a').value = t && t.age_years_est != null ? t.age_years_est : ''; $('f-plot').value = (t && t.plot_ref) || '';
    $('f-memo').value = (t && t.supplier_notes_ja) || '';
    state.form = (t && t.form_id) || null; state.season = (t && t.best_season_override) || null; state.nema = (t && t.nemawashi_status) || null;
    $('f-nema-date').value = (t && t.nemawashi_dates && t.nemawashi_dates[0]) || '';
    var ro = t && state.me.member.role === 'supplier' && ['draft', 'review'].indexOf(t.status) < 0;
    $('form').querySelectorAll('input,select,textarea,button').forEach(function (x) { if (x.id !== 'new') x.disabled = !!ro; });
    msg(ro ? 'この樹木は' + (STATUS_JA[t.status] || t.status) + 'のため編集できません。' : (t && t.status === 'review' ? '審査中です。編集すると下書きに戻ります。' : ''));
    renderChips(); renderShots();
  }
  function patchFromForm() {
    var dates = $('f-nema-date').value ? [$('f-nema-date').value] : [];
    return { species_id: $('f-species').value || null, given_name_ja: $('f-name').value, cultivar_ja: $('f-cultivar').value,
      height_cm: $('f-h').value, width_cm: $('f-w').value, trunk_girth_cm: $('f-g').value, root_ball_cm: $('f-r').value, age_years_est: $('f-a').value,
      plot_ref: $('f-plot').value, supplier_notes_ja: $('f-memo').value, form_id: state.form, best_season_override: state.season, nemawashi_status: state.nema, nemawashi_dates: dates };
  }
  function save() {
    var body = patchFromForm();
    if (!body.species_id || body.species_id === '__other__') { msg('樹種を選んでください。', true); return Promise.reject(new Error('species')); }
    if (state.tree) body.id = state.tree.id;
    msg('保存中…');
    return MeiAuth.api('tree_save', { body: body }).then(function (r) {
      if (r.status >= 300) { msg(r.data.error || '保存できませんでした', true); throw new Error(r.data.error); }
      var was = state.tree; state.tree = r.data.tree;
      $('f-no').textContent = state.tree.catalog_no; $('f-title').textContent = state.tree.given_name_ja || '樹木';
      msg(was ? '保存しました。' : '登録しました：' + state.tree.catalog_no);
      return loadTrees().then(function () { return state.tree; });
    });
  }
  function openTree(id) {
    msg('読み込み中…');
    return MeiAuth.api('tree_get', { query: { id: id } }).then(function (r) {
      if (r.status >= 300) { msg(r.data.error || '読み込めません', true); return; }
      fillForm(r.data.tree); state.media = r.data.media || []; renderShots(); msg('');
      window.scrollTo({ top: $('form').offsetTop - 12, behavior: 'smooth' });
    });
  }
  $('new').addEventListener('click', function () { fillForm(null); msg(''); });
  $('save').addEventListener('click', function () { save().catch(function () { }); });
  $('submit').addEventListener('click', function () {
    save().then(function (t) { return MeiAuth.api('tree_submit', { body: { id: t.id } }); }).then(function (r) {
      if (!r) return;
      if (r.status === 422) { var m = { species_id: '樹種', height_cm: '樹高', width_cm: '枝張り', photo: '写真（最低1枚）' }; msg('まだ足りません：' + r.data.missing.map(function (k) { return m[k] || k; }).join(' · '), true); return; }
      if (r.status >= 300) { msg(r.data.error || '提出できませんでした', true); return; }
      state.tree = r.data.tree; fillForm(state.tree); loadTrees(); msg('提出しました。スタッフが審査します。編集すると下書きに戻ります。');
    }).catch(function () { });
  });

  // ---- media ----
  function renderShots() {
    var el = $('shots'), done = 0;
    el.innerHTML = SHOTS.map(function (label, i) {
      var n = i + 1, m = state.media.filter(function (x) { return x.kind === 'photo' && x.shot_no === n; })[0];
      if (m) done++;
      return '<label class="shot' + (m ? ' done' : '') + '" data-shot="' + n + '">' + (m && m._preview ? '<img src="' + m._preview + '" alt="">' : '') + '<span>' + label + (m ? ' ✓' : '') + '</span><input type="file" accept="image/*" capture="environment" aria-label="' + label + '"></label>';
    }).join('');
    $('shot-count').textContent = done + ' / 10';
    el.querySelectorAll('input').forEach(function (inp) { inp.addEventListener('change', function () { if (inp.files[0]) uploadPhoto(+inp.parentNode.dataset.shot, inp.files[0]); }); });
    var v = state.media.filter(function (x) { return x.kind === 'video'; })[0];
    $('video-info').textContent = v ? '1本 · ' + (v.duration_s ? v.duration_s + ' 秒 · ' : '') + (v.taken_at || '') : '未登録';
    $('video-slot').classList.toggle('done', !!v);
  }
  function ensureTree() { return state.tree ? Promise.resolve(state.tree) : save(); }
  function shrink(file) {
    // → {blob, width, height}: ≤2000 px JPEG via canvas (EXIF, including GPS, does not survive re-encoding)
    return createImageBitmap(file).then(function (bmp) {
      var k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
      var c = document.createElement('canvas'); c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
      return new Promise(function (res, rej) { c.toBlob(function (b) { b ? res({ blob: b, width: c.width, height: c.height }) : rej(new Error('encode')); }, 'image/jpeg', 0.86); });
    }).catch(function () { throw new Error('この画像を読めません。iPhone は「設定 → カメラ → フォーマット → 互換性優先」にして撮り直してください（HEIC 非対応）。'); });
  }
  function putSigned(signed, blob, mime) {
    return fetch(signed.signed_url, { method: 'PUT', headers: { 'Content-Type': mime, 'x-upsert': 'false' }, body: blob }).then(function (r) { if (!r.ok) throw new Error('アップロードに失敗しました（' + r.status + '）'); });
  }
  function fileDate(file) { var d = new Date(file.lastModified || Date.now()); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function uploadPhoto(shot, file) {
    var season = state.shootSeason || seasonOfMonth(new Date().getMonth() + 1), taken = $('shoot-date').value || fileDate(file), tree;
    msg(SHOTS[shot - 1] + ' を処理中…');
    ensureTree().then(function (t) { tree = t; return shrink(file); }).then(function (img) {
      return MeiAuth.api('media_sign', { body: { tree_id: tree.id, kind: 'photo', mime: 'image/jpeg', bytes: img.blob.size } }).then(function (r) {
        if (r.status >= 300) throw new Error(r.data.error || 'sign');
        msg(SHOTS[shot - 1] + ' を送信中…');
        return putSigned(r.data, img.blob, 'image/jpeg').then(function () {
          return MeiAuth.api('media_commit', { body: { tree_id: tree.id, path: r.data.path, kind: 'photo', mime: 'image/jpeg', shot_no: shot, season: season, taken_at: taken, width: img.width, height: img.height, exif_stripped: true } });
        }).then(function (c) {
          if (c.status >= 300) throw new Error(c.data.error || 'commit');
          c.data.media._preview = URL.createObjectURL(img.blob);
          state.media = state.media.filter(function (m) { return !(m.kind === 'photo' && m.shot_no === shot); }).concat([c.data.media]);
          renderShots(); msg(SHOTS[shot - 1] + ' を登録しました。');
        });
      });
    }).catch(function (e) { msg(e.message, true); });
  }
  $('f-video').addEventListener('change', function () {
    var file = this.files[0]; if (!file) return;
    if (file.size > 500 * 1024 * 1024) { msg('動画は 500 MB までです。', true); return; }
    var url = URL.createObjectURL(file), v = document.createElement('video'); v.preload = 'metadata'; v.muted = true;
    var meta = new Promise(function (res, rej) {
      v.onloadedmetadata = function () { res({ duration: Math.round(v.duration || 0), w: v.videoWidth, h: v.videoHeight }); };
      v.onerror = function () { rej(new Error('この動画はブラウザで再生できません（HEVC？）。iPhone は「互換性優先」で撮り直してください。')); };
      v.src = url;
    });
    var tree, info;
    msg('動画を確認中…');
    Promise.all([ensureTree(), meta]).then(function (res) {
      tree = res[0]; info = res[1];
      if (!info.w) throw new Error('この動画は復号できません（HEVC？）。「互換性優先」で撮り直してください。');
      return MeiAuth.api('media_sign', { body: { tree_id: tree.id, kind: 'video', mime: file.type || 'video/mp4', bytes: file.size } });
    }).then(function (r) {
      if (r.status >= 300) throw new Error(r.data.error || 'sign');
      msg('動画を送信中…（' + Math.round(file.size / 1048576) + ' MB）');
      return putSigned(r.data, file, file.type || 'video/mp4').then(function () {
        return MeiAuth.api('media_commit', { body: { tree_id: tree.id, path: r.data.path, kind: 'video', mime: file.type || 'video/mp4', season: state.shootSeason || seasonOfMonth(new Date().getMonth() + 1), taken_at: $('shoot-date').value || fileDate(file), width: info.w, height: info.h, duration_s: info.duration } });
      });
    }).then(function (c) {
      if (c.status >= 300) throw new Error(c.data.error || 'commit');
      state.media = state.media.filter(function (m) { return m.kind !== 'video'; }).concat([c.data.media]);
      renderShots(); msg('動画を登録しました。');
    }).catch(function (e) { msg(e.message, true); }).finally(function () { URL.revokeObjectURL(url); });
  });

  // ---- boot ----
  $('logout').addEventListener('click', function (e) { e.preventDefault(); MeiAuth.logout().then(function () { location.reload(); }); });
  $('shoot-date').value = today();
  MeiAuth.requireLogin($('gate'), { title: '入 · 供給者ログイン' }).then(function () { return MeiAuth.api('me'); }).then(function (r) {
    if (r.status === 403) { $('gate').innerHTML = '<p class="muted">このアカウントはメンバーではありません。管理者にご連絡ください。</p>'; return; }
    if (r.status === 503) { $('gate').innerHTML = '<p class="muted">データベースが未接続です（環境変数）。</p>'; return; }
    if (r.status >= 300) { $('gate').innerHTML = '<p class="muted">' + esc(r.data.error || 'エラー') + '</p>'; return; }
    state.me = r.data; $('who').textContent = (r.data.member.name || r.data.user.email) + ' · ' + r.data.member.role;
    $('gate').hidden = true; $('app').hidden = false;
    return MeiAuth.api('species_all').then(function (s) { state.species = (s.data && s.data.species) || []; renderSpecies(); return loadTrees(); }).then(function () { fillForm(null); });
  }).catch(function (e) { $('gate').innerHTML = '<p class="muted">' + esc(e.message) + '</p>'; });
})();
