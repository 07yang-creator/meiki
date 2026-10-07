/* edit.js — ?edit=1 on the gallery: staff/admin replace a SAMPLE photo with a real shot (temporary, until the samples
 * are retired). Loaded by mei.js after auth.js. The server decides who may (sample_sign / sample_commit are staff-only);
 * this file only draws the buttons. Photos are re-encoded in the browser (≤2000 px JPEG) so EXIF/GPS never leave the
 * machine, PUT straight to the public bucket on a signed upsert URL, then recorded in the manifest.
 */
(function () {
  'use strict';
  var SEASON = { spring: '春', summer: '夏', autumn: '秋', winter: '冬' };
  var SHOTS = { 1: '①正面', 2: '②正面横', 3: '③¾左', 4: '④¾右', 5: '⑤背面', 6: '⑥根元', 7: '⑦幹周', 8: '⑧枝ぶり', 9: '⑨状態', 10: '⑩比例' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function bar() {
    var b = document.getElementById('sample-banner');
    if (!b) { b = document.createElement('div'); b.id = 'sample-banner'; b.className = 'sample-banner'; document.body.insertBefore(b, document.body.firstChild); }
    b.classList.add('edit-bar'); return b;
  }
  function shrink(file) {
    return createImageBitmap(file).then(function (bmp) {
      var k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
      var c = document.createElement('canvas'); c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
      return new Promise(function (res, rej) { c.toBlob(function (b) { b ? res(b) : rej(new Error('encode')); }, 'image/jpeg', 0.86); });
    }).catch(function () { throw new Error('無法讀取這張圖片（HEIC？請用 JPEG/PNG）'); });
  }
  function put(signed, blob) {
    return fetch(signed.signed_url, { method: 'PUT', headers: { 'Content-Type': 'image/jpeg', 'x-upsert': 'true' }, body: blob }).then(function (r) { if (!r.ok) throw new Error('上傳失敗（' + r.status + '）'); });
  }
  function button(slot) {
    var ph = slot.parentNode; if (!ph || ph.querySelector('.edit-btn')) return;
    var lab = document.createElement('label'); lab.className = 'edit-btn';
    lab.title = '替換範例照片：' + (SHOTS[slot.dataset.shot] || slot.dataset.shot) + ' · ' + (SEASON[slot.dataset.season] || slot.dataset.season);
    lab.innerHTML = '替換照片<input type="file" accept="image/*">';
    ph.appendChild(lab);
    lab.querySelector('input').addEventListener('change', function () { if (this.files[0]) upload(slot, ph, lab, this.files[0]); });
  }
  function upload(slot, ph, lab, file) {
    var body = { sample_id: slot.dataset.sample, shot: +slot.dataset.shot, season: slot.dataset.season };
    lab.textContent = '處理中…'; lab.classList.add('busy');
    shrink(file).then(function (blob) {
      return MeiAuth.api('sample_sign', { body: Object.assign({ mime: 'image/jpeg', bytes: blob.size }, body) }).then(function (r) {
        if (r.status >= 300) throw new Error(r.data.error || '簽名失敗');
        lab.textContent = '上傳中…';
        return put(r.data, blob);
      });
    }).then(function () { return MeiAuth.api('sample_commit', { body: body }); }).then(function (c) {
      if (c.status >= 300) throw new Error(c.data.error || '記錄失敗');
      var img = ph.querySelector('img');
      if (!img) { img = document.createElement('img'); img.alt = ''; ph.insertBefore(img, ph.firstChild); }
      img.src = c.data.src;
      ph.querySelectorAll('svg.silhouette, .cap').forEach(function (e) { e.remove(); });
      lab.classList.remove('busy'); lab.innerHTML = '已替換 · 再換<input type="file" accept="image/*">';
      lab.querySelector('input').addEventListener('change', function () { if (this.files[0]) upload(slot, ph, lab, this.files[0]); });
    }).catch(function (e) { lab.classList.remove('busy'); lab.innerHTML = esc(e.message) + ' · 重試<input type="file" accept="image/*">'; lab.querySelector('input').addEventListener('change', function () { if (this.files[0]) upload(slot, ph, lab, this.files[0]); }); });
  }
  function keepEditOnLinks() {
    document.querySelectorAll('a[href]').forEach(function (a) {
      var h = a.getAttribute('href');
      if (!h || /^(https?:|mailto:|#)/.test(h) || /[?&]edit=1/.test(h)) return;
      a.setAttribute('href', h + (h.indexOf('?') >= 0 ? '&' : '?') + 'edit=1');
    });
  }
  function activate(me) {
    bar().innerHTML = '編輯模式 · ' + esc(me.member.name || me.user.email) + ' · ' + esc(me.member.role) + ' · 點選照片角上的「替換照片」上傳實拍（範例樹）· 公開頁面最多 5 分鐘後更新 · <a href="' + esc(location.pathname + location.search.replace(/[?&]edit=1/, '').replace(/^&/, '?')) + '">登出</a>';
    document.querySelectorAll('.edit-slot').forEach(button);
    keepEditOnLinks();
  }
  function init() {
    var b = bar();
    MeiAuth.session().then(function (s) {
      if (!s) { b.innerHTML = '編輯模式 · 請先登入'; var box = document.createElement('div'); box.className = 'wrap'; box.style.paddingTop = '16px'; b.parentNode.insertBefore(box, b.nextSibling); return MeiAuth.requireLogin(box, { title: '編輯模式 · 登入', hint: 'スタッフ・管理者のみ。' }).then(function () { box.remove(); return init(); }); }
      return MeiAuth.api('me').then(function (r) {
        if (r.status === 503) { b.textContent = '編輯模式 · 資料庫未連線（環境變數）'; return; }
        if (r.status >= 300) { b.textContent = '編輯模式 · ' + (r.data.error || '無權限'); return; }
        if (['admin', 'staff'].indexOf(r.data.member.role) < 0) { b.textContent = '編輯模式 · 僅限工作人員（staff / admin）替換照片'; return; }
        activate(r.data);
      });
    }).catch(function (e) { b.textContent = '編輯模式 · ' + e.message; });
  }
  window.MeiEdit = { init: init };
  init();
})();
