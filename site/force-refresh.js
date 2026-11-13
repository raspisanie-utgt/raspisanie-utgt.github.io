(function () {
  'use strict';
  var busy = false;
  async function refresh() {
    if (busy) return;
    if (!navigator.onLine) { alert('Для обновления нужен интернет. Подключитесь к сети и повторите.'); return; }
    busy = true;
    var buttons = [document.getElementById('forceRefresh'), document.getElementById('forceRefreshAppearance')];
    buttons.forEach(function (b) { if (b) { b.disabled = true; b.textContent = 'Загружаем новую версию…'; } });
    try {
      // Do not erase localStorage: group, theme, appearance, and other preferences remain.
      // First verify the origin is reachable; otherwise keep the offline copy intact.
      var check = await fetch('./?refresh-check=' + Date.now(), { cache: 'no-store' });
      if (!check.ok || check.headers.get('X-Utgt-Saved') === '1') throw new Error('Сервер недоступен');
      if ('serviceWorker' in navigator) {
        var registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.filter(function (r) { return r.scope.startsWith(location.origin + location.pathname.replace(/[^/]*$/, '')); }).map(function (r) { return r.unregister(); }));
      }
      if ('caches' in window) {
        var keys = await caches.keys();
        await Promise.all(keys.filter(function (k) { return k.indexOf('utgt-') === 0; }).map(function (k) { return caches.delete(k); }));
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
