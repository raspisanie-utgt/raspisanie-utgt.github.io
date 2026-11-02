// Вёрстка: все группы × «Сегодня/Завтра/Неделя» × 12 ширин экрана (280…3440, с 21:9) + крупный шрифт (×1.3, ×1.6),
// светлая и тёмная тема. Всё раскрыто. Ничего не вылезает за карточки и экран, текст не обрезается,
// длинное в окнах листается.
const { URL, WIDTHS, groups, launch, page, report, tab, openWhere, openHistory } = require('./lib');

function layoutCheck() {
  const bad = [];
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > vw + 1) bad.push('страница шире экрана: ' + document.documentElement.scrollWidth + ' > ' + vw);
  const name = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\s+/).join('.') : '');
  const txt = (el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  const hidden = (el) => { for (let a = el; a; a = a.parentElement) { const s = getComputedStyle(a); if (parseFloat(s.opacity) < 0.05 || s.visibility === 'hidden') return true; } return false; };
  // вылезает за свою карточку по ширине
  const boxes = '.lesson, .wday, .tlesson, .banner, .base, .news, .calendar li, .tabs button, dialog[open], .list, .hday, details, .install, .group-chip, .seg button, .tlist button, .course button, .where-out, .where-list button, .office';
  document.querySelectorAll(boxes).forEach((box) => {
    if (!box.offsetParent && box.tagName !== 'DIALOG') return;
    const b = box.getBoundingClientRect(); if (!b.width) return;
    const scrollsX = ['auto', 'scroll'].includes(getComputedStyle(box).overflowX);
    if (scrollsX) return;
    box.querySelectorAll('*').forEach((el) => {
      if (!el.offsetParent || getComputedStyle(el).position === 'absolute' || el.closest('.sr')) return;
      if (el.closest('.full') && !box.classList.contains('open')) return;
      if (el.closest('[style*="overflow-x"], .hday')) return;
      const r = el.getBoundingClientRect(); if (!r.width || !r.height) return;
      if (r.right > b.right + 1 || r.left < b.left - 1) bad.push('вылезает: ' + name(box) + ' > ' + name(el) + ' «' + txt(el) + '» на ' + Math.round(Math.max(r.right - b.right, b.left - r.left)) + 'px');
    });
  });
  // обрезанный текст
  document.querySelectorAll('body *').forEach((el) => {
    if (!el.offsetParent && el.tagName !== 'DIALOG') return;
    if (el.closest('.sr, .snake') || el.matches('a.crop') || hidden(el)) return;
    const cs = getComputedStyle(el);
    if (el.getAnimations().length) return;
    if (['hidden', 'clip'].includes(cs.overflowY) && el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 2) bad.push('обрезано по высоте: ' + name(el) + ' (' + el.clientHeight + ' из ' + el.scrollHeight + ') «' + txt(el) + '»');
    if (['hidden', 'clip'].includes(cs.overflowX) && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2 && cs.textOverflow !== 'ellipsis') bad.push('обрезано по ширине: ' + name(el) + ' «' + txt(el) + '»');
  });
  // длинное содержимое окна должно листаться
  const d = document.querySelector('dialog[open]');
  if (d) {
    const all = [d, ...d.querySelectorAll('*')], db = d.getBoundingClientRect();
    const bottom = Math.max(...all.map((e) => e.getBoundingClientRect().bottom));
    if (bottom > db.bottom + 2 && !all.some((e) => ['auto', 'scroll'].includes(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 2)) bad.push('окно ' + d.id + ': содержимое ниже окна и не листается');
  }
  return [...new Set(bad)];
}
const openAll = (p) => p.evaluate(() => {
  document.querySelectorAll('details').forEach((d) => { if (!d.hidden) d.open = true; });
  document.querySelectorAll('.lesson, .tlesson, .wday[role=button], .base li[role=button]').forEach((l) => l.classList.add('open'));
});

(async () => {
  const b = await launch(); const problems = [];
  // крупный масштаб в настройках телефона («Размер экрана») = экран для сайта уже: 393 px при ×1.3 и ×1.6
  const sets = WIDTHS.map((x) => ({ ...x, scale: 1 })).concat([{ w: 302, h: 615, mob: true, scale: 1.3 }, { w: 246, h: 500, mob: true, scale: 1.6, dark: true }]);
  // W=280,246 — только выбранные ширины
  for (const s of sets.filter((x) => !process.env.W || process.env.W.split(',').includes(String(x.w)))) {
    const p = await page(b, { w: s.w, h: s.h, mob: s.mob, dark: s.dark || s.w === 1920 || s.w === 280 || s.w === 2560, scale: 1 });
    const tag = s.w + 'px' + (s.scale !== 1 ? ' (393 при масштабе ×' + s.scale + ')' : '');
    const check = async (where) => { await p.waitForTimeout(800); await openAll(p); await p.waitForTimeout(900); (await p.evaluate(layoutCheck)).forEach((x) => problems.push(tag + ', ' + where + ': ' + x)); };
    const all = s.w === 393 || s.w === 320 || s.scale !== 1 ? groups() : ['11-А', '21-С', '31-Д', '41-П', '41-С'];
    for (const g of all) {
      try {
        await p.goto(URL + '?group=' + encodeURIComponent(g)); await p.waitForSelector('#list .lesson, #list .empty');
        await check(g + ' сегодня');
        await tab(p, '1'); await check(g + ' завтра');
        await tab(p, 'week'); await check(g + ' неделя');
      } catch (e) { problems.push(tag + ', ' + g + ': не удалось — ' + e.message.split('\n')[0]); }
    }
    for (const t of ['Певцова Л.А.', 'Рыжикова Т.П.', 'Мигальникова О.А.']) {
      try {
        await p.goto(URL + '?teacher=' + encodeURIComponent(t)); await p.waitForSelector('.tlesson, .empty'); await check(t);
        await tab(p, 'week'); await check(t + ' неделя');
      } catch (e) { problems.push(tag + ', ' + t + ': не удалось — ' + e.message.split('\n')[0]); }
    }
    try {
      await p.goto(URL + '?group=11-%D0%90'); await p.waitForSelector('#list .lesson, #list .empty');
      // «Где сейчас преподаватель» с ответом
      await openWhere(p);
      await p.waitForSelector('#whereList button', { timeout: 8000 }); await p.click('#whereList button'); await check('где сейчас преподаватель');
      if (await p.$('#panel[open]')) { await p.keyboard.press('Escape'); await p.waitForTimeout(300); }
      await p.click('#groupBtn'); await check('выбор группы');
      await p.click('#whoSeg button[data-who="teacher"]'); await p.waitForTimeout(800); await check('выбор преподавателя');
      await p.keyboard.press('Escape');
      await openHistory(p); await p.waitForSelector('#historyList details'); await check('история замен');
      await p.keyboard.press('Escape');
    } catch (e) { problems.push(tag + ', окна: не удалось — ' + e.message.split('\n')[0]); }
    problems.push(...p.errs.map((x) => tag + ': ' + x));
    console.log(tag, 'готово');
    await p.ctx.close();
  }
  await b.close();
  report('Вёрстка на всех экранах', problems);
})();
