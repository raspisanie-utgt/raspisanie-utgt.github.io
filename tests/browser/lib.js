// Общее для проверок в браузере (Playwright). Каждая проверка — отдельный файл:
//   node tests/browser/<файл>.js <адрес сайта>
// Последняя строка вывода — «ИТОГ: проблем N»; run.sh собирает их в сводку.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'));
const URL = (process.argv[2] || 'http://localhost:8800/').replace(/\/?$/, '/');
const SHOTS = process.env.SHOTS || path.join(ROOT, '_proverka');
fs.mkdirSync(SHOTS, { recursive: true });

const groups = () => read('data/groups/index.json').groups.map((g) => g.group);
const zdays = () => read('data/zameny/index.json').days;
// «Сейчас» для проверок с часами: последний день, на который есть замены, 11:00 (идёт 2-я пара)
const lastZ = () => zdays().slice(-1)[0];
const NOW = () => new Date((process.env.NOW_DATE || lastZ()) + 'T11:00:00+03:00');

const WIDTHS = [
  { w: 280, h: 640, mob: true }, { w: 320, h: 640, mob: true }, { w: 360, h: 760, mob: true },
  { w: 393, h: 800, mob: true }, { w: 430, h: 900, mob: true }, { w: 768, h: 1000, mob: true },
  { w: 1024, h: 768, mob: false }, { w: 1366, h: 768, mob: false }, { w: 1920, h: 1000, mob: false },
  // 21:9 — вытянутый телефон и широкие мониторы (там третий день столбцом)
  { w: 412, h: 960, mob: true }, { w: 2560, h: 1080, mob: false }, { w: 3440, h: 1440, mob: false },
  // планшет лёжа (сенсорный — тоже раскладка для компьютера), вертикальный монитор, 32:9
  { w: 1180, h: 820, mob: true }, { w: 1080, h: 1920, mob: false }, { w: 5120, h: 1440, mob: false },
];

async function launch() { return chromium.launch(); }

// Новая страница: ошибки скриптов, ошибки в консоли и упавшие запросы к своему сайту — в errs
async function page(browser, { w = 393, h = 800, mob = true, dark = false, now = true, sw = 'block', scale = 2 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob,
    colorScheme: dark ? 'dark' : 'light', deviceScaleFactor: scale, serviceWorkers: sw });
  const p = await ctx.newPage();
  p.errs = [];
  p.on('pageerror', (e) => p.errs.push('JS: ' + String(e).split('\n')[0]));
  p.on('console', (m) => { if (m.type() === 'error' && !/favicon|ERR_INTERNET_DISCONNECTED|net::ERR/.test(m.text())) p.errs.push('консоль: ' + m.text().slice(0, 160)); });
  p.on('requestfailed', (r) => { if (r.url().startsWith(URL) && !r.url().includes('health.json?net=') && !/net::ERR_ABORTED|INTERNET_DISCONNECTED/.test(r.failure().errorText)) p.errs.push('запрос: ' + r.url().replace(URL, '') + ' ' + r.failure().errorText); });
  p.on('response', (r) => { if (r.url().startsWith(URL) && r.status() >= 400) p.errs.push('ответ ' + r.status() + ': ' + r.url().replace(URL, '')); });
  if (now) await p.clock.install({ time: NOW() });
  p.ctx = ctx;
  return p;
}

async function open(p, query = '?group=' + encodeURIComponent('11-А')) {
  await p.goto(URL + query);
  await p.waitForSelector('#list .lesson, #list .empty, .tlesson, .empty', { timeout: 20000 });
  await p.waitForTimeout(700);
}

// День: кнопка полосы дней (две недели без воскресений и «Неделя»), пока полоса не построена — старая вкладка.
// «Завтра» может не быть в полосе (воскресенье) — тогда следующий день после выбранного.
async function tab(p, d) {
  let el = p.locator('.tabs button[data-day="' + d + '"]:visible').first();
  if (String(d) === '1' && !(await el.count())) el = p.locator('.tabs .strip[aria-selected="true"] ~ .strip:not(.wk):visible').first();
  await el.click();
}

// «Где преподаватель» и «История замен»: на телефоне — в раскрывающихся блоках, на компьютере — плитками справа
async function openWhere(p) {
  const t = p.locator('#tiles [data-tile="where"]');
  if (await t.isVisible()) await t.click();
  else await p.evaluate(() => { const d = document.getElementById('whereD'); d.open = true; d.scrollIntoView(); });
}
async function openHistory(p) {
  const t = p.locator('#tiles [data-tile="history"]');
  if (await t.isVisible()) return t.click();
  await p.evaluate(() => { document.getElementById('useful').open = true; }); await p.waitForTimeout(200);
  await p.click('#historyBtn');
}

// Сводка: печатает найденное (не больше 40 строк) и итог
function report(name, problems) {
  console.log(`\n=== ${name}`);
  [...new Set(problems)].slice(0, 40).forEach((x) => console.log('  - ' + x));
  if (problems.length > 40) console.log(`  … и ещё ${problems.length - 40}`);
  console.log(`ИТОГ: проблем ${problems.length}`);
}

module.exports = { ROOT, read, URL, SHOTS, groups, zdays, lastZ, NOW, WIDTHS, launch, page, open, report, tab, openWhere, openHistory };
