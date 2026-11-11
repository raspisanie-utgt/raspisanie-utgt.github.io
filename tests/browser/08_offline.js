// Без интернета и обновления: офлайн-кеш ставится с первого захода, без сети показывает сохранённое
// и значок «нет интернета»; медленная сеть — сохранённое с пометкой; новая версия сайта применяется сама;
// подсказки установки приложения в разных браузерах.
const fs = require('fs'), os = require('os'), path = require('path'), http = require('http');
const { ROOT, URL, launch, report } = require('./lib');
const { chromium } = require('playwright');

function serve(dir, network) {
  const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml' };
  const srv = http.createServer((req, res) => {
    const pathname = decodeURIComponent(req.url.split('?')[0]);
    if (network.unavailable && pathname === '/data/groups/11a.json') {
      res.writeHead(503); return res.end();
    }
    let f = path.join(dir, pathname);
    if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
    if (!fs.existsSync(f)) { res.writeHead(404); return res.end(); }
    function send() {
      if (res.destroyed) return;
      res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
      fs.createReadStream(f).pipe(res);
    }
    if (network.slow && /^\/data\/.*\.json$/.test(pathname)) setTimeout(send, 2500);
    else send();
  });
  return new Promise((ok) => srv.listen(0, () => ok({ srv, url: 'http://localhost:' + srv.address().port + '/' })));
}

(async () => {
  const P = []; const ok = (c, m) => { if (!c) P.push(m); };
  const b = await launch();
  // своя копия сайта — чтобы подменить версию
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'site-'));
  fs.cpSync(path.join(ROOT, '_site'), dir, { recursive: true });
  const network = { unavailable: false, slow: false };
  const { srv, url } = await serve(dir, network);
  try {
    const ctx = await b.newContext({ viewport: { width: 393, height: 800 }, isMobile: true, hasTouch: true });
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', (e) => errs.push(String(e)));
    await p.goto(url + '?group=11-%D0%90'); await p.waitForSelector('#list .lesson, #list .empty');
    const sw = await p.waitForFunction(() => navigator.serviceWorker && navigator.serviceWorker.controller, null, { timeout: 20000 }).then(() => true, () => false);
    ok(sw, 'офлайн-кеш не включился с первого захода');
    await p.waitForTimeout(1500);
    // без интернета
    await ctx.setOffline(true);
    await p.reload(); const shown = await p.waitForSelector('#list .lesson, #list .empty', { timeout: 15000 }).then(() => true, () => false);
    ok(shown, 'без интернета расписание не показалось');
    await p.waitForTimeout(800);
    ok((await p.evaluate(() => document.getElementById('netBtn').className)).includes('off'), 'без интернета значок не «нет интернета»');
    for (const g of ['21-С', '41-П']) {
      await p.goto(url + '?group=' + encodeURIComponent(g)).catch(() => {});
      ok(await p.waitForSelector('#list .lesson, #list .empty', { timeout: 10000 }).then(() => true, () => false), 'без интернета не открылась группа ' + g);
    }
    await ctx.setOffline(false);
    // 503 отдаёт сам сервер, чтобы запрос прошёл через реальный service worker.
    network.unavailable = true;
    await p.goto(url + '?group=11-%D0%90&date=2026-11-11');
    ok(await p.locator('#list .lesson').first().waitFor({ timeout: 10000 }).then(() => true, () => false),
      'HTTP 503: расписание из офлайн-кэша не показалось');
    ok(/показано сохранённое/i.test(await p.locator('#netBtn').getAttribute('aria-label')),
      'HTTP 503: расписание из кэша не помечено как сохранённое');
    network.unavailable = false;
    await ctx.setOffline(true);
    await ctx.setOffline(false);
    ok(await p.waitForFunction(() => !/показано сохранённое/i.test(document.getElementById('netBtn').getAttribute('aria-label')),
      null, { timeout: 10000 }).then(() => true, () => false), 'после восстановления сети всё ещё показан кэш');
    // медленная сеть: страница из сохранённого, пометка «медленный»
    network.slow = true;
    await p.goto(url + '?group=11-%D0%90'); await p.waitForSelector('#list .lesson, #list .empty'); await p.waitForTimeout(1500);
    ok((await p.evaluate(() => document.getElementById('netBtn').className)).includes('slow'), 'медленная сеть: значок не «медленный»');
    network.slow = false;
    // новая версия: меняем текст и версию кеша — страница должна обновиться сама
    fs.writeFileSync(path.join(dir, 'index.html'), fs.readFileSync(path.join(dir, 'index.html'), 'utf8').replace('Если нажать на урок', 'ПРОВЕРКА нажать на урок'));
    fs.writeFileSync(path.join(dir, 'sw.js'), fs.readFileSync(path.join(dir, 'sw.js'), 'utf8').replace(/utgt-[0-9a-f]+/, 'utgt-proverka'));
    await ctx.route(url, async (r) => { await new Promise((x) => setTimeout(x, 2000)); r.continue().catch(() => {}); });
    await p.goto(url + '?group=11-%D0%90'); let got = false;
    for (let i = 0; i < 30 && !got; i++) { await p.waitForTimeout(1000); got = await p.evaluate(() => (document.getElementById('lessonHint') || {}).textContent || '').then((t) => t.startsWith('ПРОВЕРКА'), () => false); }
    ok(got, 'новая версия сайта не применилась сама за 30 с');
    errs.forEach((e) => P.push('JS: ' + e));
    await ctx.close();
  } finally { srv.close(); fs.rmSync(dir, { recursive: true, force: true }); }

  // подсказки установки приложения
  const UA = {
    'iPhone Safari': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
    'iPhone Chrome': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/126.0 Mobile/15E148 Safari/604.1',
    'Android Chrome': 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36',
    'Android Яндекс': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 YaBrowser/24.6 Mobile Safari/537.36',
    'Android Samsung': 'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0 Mobile Safari/537.36',
    'Телеграм': 'Mozilla/5.0 (Linux; Android 14; Pixel 7; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0 Mobile Safari/537.36 Telegram-Android/11.0',
    'ВК': 'Mozilla/5.0 (Linux; Android 14; Pixel 7; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0 Mobile Safari/537.36 VKAndroidApp/8.0',
  };
  for (const [name, ua] of Object.entries(UA)) {
    const c = await b.newContext({ userAgent: ua, viewport: { width: 390, height: 800 } }); const q = await c.newPage(); const errs = []; q.on('pageerror', (e) => errs.push(String(e)));
    await q.goto(URL + '?group=11-%D0%90'); await q.waitForSelector('#list .lesson, #list .empty');
    await q.evaluate(() => { document.getElementById('useful').open = true; }); await q.waitForTimeout(300);
    const t = await q.$eval('.install', (e) => e.innerText.trim()).catch(() => '');
    ok(t.length > 10, 'установка приложения: нет подсказки в «' + name + '»');
    errs.forEach((e) => P.push(name + ': ' + e)); await c.close();
  }
  await b.close();
  report('Без интернета, обновление, установка', P);
})();
