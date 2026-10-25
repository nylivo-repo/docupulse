// Applies the saved theme and light/dark choice before the app loads (see src/app/core/theme.ts).
// A separate file, not inline, so the Content-Security-Policy can forbid inline scripts.
(function () {
  var a = {};
  try { a = JSON.parse(localStorage.getItem('idp-appearance') || '{}'); } catch (e) {}
  var m = a.mode === 'light' || a.mode === 'dark' ? a.mode
    : (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.setAttribute('data-mode', m);
  document.documentElement.setAttribute('data-theme', a.theme || 'indigo');
})();
