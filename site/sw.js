// Работа без интернета. Страница и данные (расписания, замены): сначала сеть — чтобы замены были
// свежими, — а без сети последнее сохранённое. Файлы с ?v=… (стили, скрипты) не меняются — из кэша.
// __BUILD__ подставляет build_site.py: новая сборка = новый кэш, старый удаляется.
var CACHE = "utgt-__BUILD__";

// Сразу при установке сохраняем всё, что нужно для работы без интернета: страницу, стили и скрипты
// (их адреса с ?v=… берём из самой страницы), общие данные, расписания всех групп и последние замены.
var CORE = ["data/groups/index.json", "data/bells.json", "data/zameny/index.json", "status.json", "data/calendar.json",
  "data/news.json", "data/teachers.json", "data/info.json", "data/rooms.json", "manifest.webmanifest", "icons/icon-192.png"];

function keyOf(u) { var x = new URL(u, location.href); return x.searchParams.has("v") ? x.href : x.origin + x.pathname; }

function precache(c) {
  // must — без этого файла сайт без интернета не откроется: не скачался — установка новой версии не засчитывается,
  // и остаются старый работник и старый кэш (иначе обрыв связи посреди обновления оставил бы телефон без офлайна)
  var put = function (u, must) {
    var k = keyOf(u);
    // стили и скрипты с ?v=… не меняются: если такой уже лежит в прошлом кэше — берём оттуда, не качаем заново
    var old = /[?&]v=/.test(u) ? caches.match(k) : Promise.resolve(null);
    var p = old.then(function (hit) {
      return hit || fetch(u, { cache: "no-cache" }).then(function (r) { return r.ok ? r : null; });
    }).then(function (r) {
      if (!r) throw new Error("не скачался " + u);
      return c.put(k, r);
    });
    return must ? p : p.catch(function () {});
  };
  return fetch("./", { cache: "no-cache" }).then(function (r) {
    if (!r.ok) throw new Error("не скачалась страница");
    return r.clone().text().then(function (html) {
      var assets = (html.match(/(?:src|href)="([\w.-]+\.(?:js|css)\?v=[0-9a-f]+)"/g) || [])
        .map(function (m) { return m.replace(/^(?:src|href)="|"$/g, ""); });
      return c.put(new URL("./", location.href).href, r).then(function () {
        return Promise.all(assets.map(function (u) { return put(u, true); }));
      }).then(function () {
        return Promise.all(CORE.map(function (u) { return put(u, false); }));
      });
    });
  }).then(function () {
    return Promise.all([
      fetch("data/groups/index.json").then(function (r) { return r.json(); }).then(function (ix) {
        return Promise.all(ix.groups.map(function (g) { return put("data/groups/" + g.file); }));
      }),
      fetch("data/zameny/index.json").then(function (r) { return r.json(); }).then(function (ix) {
        return Promise.all(ix.days.slice(-4).map(function (d) { return put("data/zameny/" + d + ".json"); }));
      })
    ]).catch(function () {});
  });
}

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(precache).then(function () { return self.skipWaiting(); }, function (err) {
    return caches.delete(CACHE).then(function () { throw err; });  // недокачанный кэш не оставляем
  }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

// Картинки распоряжений и истории кэшируются по ходу просмотра — держим не больше 60 последних
function trimImages(c) {
  return c.keys().then(function (keys) {
    var imgs = keys.filter(function (r) { return /\.(png|webp|jpe?g)$/i.test(new URL(r.url).pathname); });
    return Promise.all(imgs.slice(0, Math.max(0, imgs.length - 60)).map(function (r) { return c.delete(r); }));
  });
}

function fromNetwork(req, key) {
  return fetch(req).then(function (res) {
    if (res && res.ok) {
      var copy = res.clone();
      caches.open(CACHE).then(function (c) {
        return c.put(key || req.url, copy).then(function () { if (/\.(png|webp|jpe?g)$/i.test(new URL(req.url).pathname)) return trimImages(c); });
      });
    }
    return res;
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (url.searchParams.has("v")) {
    // стили и скрипты с версией — неизменны
    e.respondWith(caches.match(req).then(function (hit) { return hit || fromNetwork(req); }));
    return;
  }
  // страница (с любыми ?group=…) хранится под одним ключом
  // (другие страницы, например privacy.html, — под своим адресом, чтобы не подменить главную)
  var root = new URL("./", location.href);
  var main = req.mode === "navigate" && (url.pathname === root.pathname || url.pathname === root.pathname + "index.html");
  var key = main ? root.href : url.origin + url.pathname;
  // медленный интернет: если сеть не ответила за 1 с (страница) или 1,5 с (данные), а сохранённая копия
  // есть — сразу она. На обычном интернете ответ приходит быстрее, и показывается свежее.
  // (сеть при этом догружает свежее в кэш для следующего раза)
  var net = fromNetwork(req, key);
  // сохранённая копия с пометкой — сайт по ней показывает «Показано сохранённое»
  var saved = function () {
    return caches.match(key)
      .then(function (hit) {
        if (!hit) return hit;
        return hit.blob().then(function (body) {
          var h = new Headers(hit.headers);
          h.set("X-Utgt-Saved", "1");
          return new Response(body, { status: hit.status, statusText: hit.statusText, headers: h });
        });
      });
  };
  e.respondWith(new Promise(function (resolve, reject) {
    var done = false;
    var timer = setTimeout(function () {
      saved().then(function (hit) { if (hit && !done) { done = true; resolve(hit); } });
    }, req.mode === "navigate" ? 1000 : 1500);
    net.then(function (res) { if (!done) { done = true; clearTimeout(timer); resolve(res); } }, function () {
      clearTimeout(timer);
      saved().then(function (hit) { if (!done) { done = true; hit ? resolve(hit) : reject(new Error("нет сети")); } });
    });
  }));
});
