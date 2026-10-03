/* auth.js — 名木 Mei auth client (members only: supplier · staff · admin). ~150 lines, flag-free.
 * The server is the security boundary: every API call carries a FRESH Supabase access token and api/mei.py
 * re-validates it on every request. What this file decides is cosmetic: which view to render.
 * Invariants (inherited from Rakusalab): gate IN PLACE for guests (never hard-redirect); the indeterminate
 * state renders the guest view; returnTo must be a same-origin path.
 */
(function () {
  'use strict';
  var CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2';   // members are in Japan; the public gallery never loads this
  var BASE = (document.querySelector('meta[name="mei-base"]') || {}).content || '/';
  var API = BASE + 'api/mei';
  var _client = null, _cfg = null, _token = '';

  function loadScript(src) {
    return new Promise(function (res, rej) {
      if (window.supabase && window.supabase.createClient) return res();
      var s = document.createElement('script'); s.src = src; s.async = true;
      s.onload = res; s.onerror = function () { rej(new Error('supabase-js の読み込みに失敗しました')); };
      document.head.appendChild(s);
    });
  }
  function client() {
    if (_client) return Promise.resolve(_client);
    return fetch(API + '?action=client_config').then(function (r) { return r.json(); }).then(function (cfg) {
      _cfg = cfg;
      if (!cfg.supabase_url || !cfg.supabase_anon_key) throw new Error('認証設定がありません（SUPABASE_URL / ANON KEY）');
      return loadScript(CDN);
    }).then(function () {
      _client = window.supabase.createClient(_cfg.supabase_url, _cfg.supabase_anon_key, { auth: { persistSession: true, autoRefreshToken: true } });
      _client.auth.onAuthStateChange(function (_e, session) { _token = (session && session.access_token) || ''; });
      return _client;
    });
  }
  function session() {
    return client().then(function (c) { return c.auth.getSession(); }).then(function (r) {
      var s = r && r.data && r.data.session; _token = (s && s.access_token) || ''; return s || null;
    });
  }
  function getToken() {
    if (!_client) return Promise.resolve(_token || '');
    return _client.auth.getSession().then(function (r) {
      var s = r && r.data && r.data.session; if (!s) return '';
      var expMs = (s.expires_at || 0) * 1000;
      if (expMs && expMs - Date.now() < 120000) {
        return _client.auth.refreshSession().then(function (r2) { var s2 = (r2 && r2.data && r2.data.session) || s; _token = s2.access_token || ''; return _token; })
          .catch(function () { _token = s.access_token || ''; return _token; });
      }
      _token = s.access_token || ''; return _token;
    }).catch(function () { return _token || ''; });
  }
  function login(email, password) {
    return client().then(function (c) { return c.auth.signInWithPassword({ email: email, password: password }); }).then(function (r) {
      if (r.error) throw new Error(r.error.message === 'Invalid login credentials' ? 'メールアドレスまたはパスワードが違います' : r.error.message);
      _token = r.data.session.access_token; return r.data.session;
    });
  }
  function logout() { return client().then(function (c) { return c.auth.signOut(); }).then(function () { _token = ''; }); }

  /* api(action, {method, body, query}) → Promise<{status, data}>; always a fresh token. */
  function api(action, opts) {
    opts = opts || {};
    var q = new URLSearchParams(opts.query || {}); q.set('action', action);
    return getToken().then(function (tok) {
      var h = { 'Accept': 'application/json' };
      if (tok) h['Authorization'] = 'Bearer ' + tok;
      if (opts.body) h['Content-Type'] = 'application/json';
      return fetch(API + '?' + q.toString(), { method: opts.method || (opts.body ? 'POST' : 'GET'), headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined });
    }).then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }, function () { return { status: r.status, data: {} }; }); });
  }

  /* Gate in place: renders a login box inside `el` when there is no session, then resolves with the session. */
  function requireLogin(el, copy) {
    copy = copy || {};
    return session().then(function (s) {
      if (s) return s;
      return new Promise(function (resolve) {
        el.innerHTML = '<form class="stack card" style="gap:12px;padding:20px 18px;max-width:420px" autocomplete="on">' +
          '<p class="dja" style="font-size:18px">' + (copy.title || 'ログイン') + '</p>' +
          '<p class="muted" style="font-size:13px">' + (copy.hint || 'メンバーのみ。招待メールのパスワードでお入りください。') + '</p>' +
          '<label class="muted" style="font-size:12px" for="au-email">メール</label><input id="au-email" class="input" style="border-radius:8px" type="email" autocomplete="username" required>' +
          '<label class="muted" style="font-size:12px" for="au-pw">パスワード</label><input id="au-pw" class="input" style="border-radius:8px" type="password" autocomplete="current-password" required>' +
          '<button type="submit" class="btn" style="height:48px;font-size:15px">入る</button><p id="au-err" class="muted" style="font-size:12px;min-height:16px" aria-live="polite"></p></form>';
        var f = el.querySelector('form');
        f.addEventListener('submit', function (e) {
          e.preventDefault();
          var err = el.querySelector('#au-err'); err.textContent = '確認中…';
          login(el.querySelector('#au-email').value.trim(), el.querySelector('#au-pw').value).then(function (s2) { el.innerHTML = ''; resolve(s2); })
            .catch(function (ex) { err.textContent = ex.message; });
        });
      });
    });
  }
  function sameOriginPath(p) { return typeof p === 'string' && /^\/(?!\/)/.test(p) ? p : null; }

  window.MeiAuth = { client: client, session: session, getToken: getToken, login: login, logout: logout, api: api, requireLogin: requireLogin, sameOriginPath: sameOriginPath, apiBase: API };
})();
