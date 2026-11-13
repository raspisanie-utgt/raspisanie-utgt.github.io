(function () {
  'use strict';
  var busy = false;
  async function refresh() {
    if (busy) return;
    busy = true;
    var buttons = [document.getElementById('forceRefresh'), document.getElementById('forceRefreshAppearance')];
    buttons.forEach(function (b) { if (b) { b.disabled = true; b.textContent = 'Загружаем новую версию…'; } });
    try {
      // Do not erase localStorage: group, theme, appearance, and other preferences remain.
      // First verify the origin is reachable; otherwise keep the offline copy intact.
      // HEAD requests bypass our service worker, so a stale offline response cannot masquerade as fresh.
      var check = await fetch('./?refresh-check=' + Date.now(), { method: 'HEAD', cache: 'no-store' });
      if (!check.ok) throw new Error('Сервер недоступен');
      if ('serviceWorker' in navigator) {
        var registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.filter(function (r) { return location.href.startsWith(r.scope); }).map(function (r) { return r.unregister(); }));
      }
      if ('caches' in window) {
        var keys = await caches.keys();
        await Promise.all(keys.filter(function (k) { return k.indexOf(location.pathname.includes('/utgt-visual-preview-') ? 'utgt-preview-' : 'utgt-') === 0 && (location.pathname.includes('/utgt-visual-preview-') || k.indexOf('utgt-preview-') !== 0); }).map(function (k) { return caches.delete(k); }));
      }
      var url = new URL(location.href);
      url.searchParams.set('force-refresh', String(Date.now()));
      location.replace(url.href);
    } catch (err) {
      buttons.forEach(function (b) { if (b) { b.disabled = false; b.textContent = '↻ Принудительно обновить сайт'; } });
      busy = false;
      alert('Не удалось загрузить свежую версию. Попробуйте позже — сохранённые данные не удалены.');
    }
  }
  ['forceRefresh', 'forceRefreshAppearance'].forEach(function (id) {
    var b = document.getElementById(id);
    if (b) b.addEventListener('click', refresh);
  });
})();
