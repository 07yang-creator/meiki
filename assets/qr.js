/* qr.js — QR placeholder until the vendored encoder lands (plan: a vendored MIT QR encoder, no CDN — the audience is in China).
 * window.MeiQR(text, size) → SVG string. Today it draws a labelled frame so layouts are honest about the slot. */
(function () {
  window.MeiQR = function (text, size) {
    size = size || 64;
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 64 64" role="img" aria-label="二维码 · 本页链接">' +
      '<rect width="64" height="64" rx="4" fill="#FFFFFF"></rect>' +
      '<rect x="6" y="6" width="16" height="16" rx="3" fill="#1C1A17"></rect><rect x="9" y="9" width="10" height="10" fill="#FFFFFF"></rect><rect x="12" y="12" width="4" height="4" fill="#1C1A17"></rect>' +
      '<rect x="42" y="6" width="16" height="16" rx="3" fill="#1C1A17"></rect><rect x="45" y="9" width="10" height="10" fill="#FFFFFF"></rect><rect x="48" y="12" width="4" height="4" fill="#1C1A17"></rect>' +
      '<rect x="6" y="42" width="16" height="16" rx="3" fill="#1C1A17"></rect><rect x="9" y="45" width="10" height="10" fill="#FFFFFF"></rect><rect x="12" y="48" width="4" height="4" fill="#1C1A17"></rect>' +
      '<text x="42" y="56" font-size="9" font-family="system-ui, sans-serif" fill="#5E5952">QR</text></svg>';
  };
})();
