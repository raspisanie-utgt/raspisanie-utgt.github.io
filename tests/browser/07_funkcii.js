// Каждая функция сайта по отдельности, по нескольку раз: выбор группы/преподавателя, история замен,
// кнопка «i», значок интернета, метки отсчёта, «где преподаватель», змейка, счётчик, свайпы, тема,
// подгруппа, неправильные адреса, часы после смены минуты.
const { URL, lastZ, launch, page, open, report, tab, openWhere, openHistory } = require('./lib');
(async () => {
  const b = await launch(); const P = []; const ok = (c, msg) => { if (!c) P.push(msg); };
  const step = async (name, fn) => { try { await fn(); } catch (e) { P.push(name + ': не удалось — ' + e.message.split('\n')[0]); } };
  for (const s of [{ w: 393, mob: true }, { w: 1366, mob: false }]) {
    const T = s.w + 'px ';
    const p = await page(b, { w: s.w, h: 800, mob: s.mob });
    await open(p);

    await step(T + 'выбор группы и преподавателя', async () => {
      for (let i = 0; i < 6; i++) {
        await p.click('#groupBtn'); await p.waitForTimeout(250);
        for (let k = 0; k < 4; k++) { await p.click('#whoSeg button[data-who="' + (k % 2 ? 'group' : 'teacher') + '"]'); await p.waitForTimeout(120); }
        await p.keyboard.press('Escape'); await p.waitForTimeout(250);
      }
      ok(!(await p.$('dialog[open]')), T + 'окно выбора не закрылось по Esc');
      await p.click('#groupBtn'); await p.click('#courses button[data-group="21-С"]'); await p.waitForTimeout(900);
      ok((await p.textContent('#groupName')).includes('21-С') || (await p.evaluate(() => location.search)).includes('21'), T + 'группа 21-С не выбралась');
      await p.click('#groupBtn'); await p.click('#whoSeg button[data-who="teacher"]'); await p.waitForSelector('#teacherList button[data-teacher]');
      await p.click('#teacherList button[data-teacher]'); await p.waitForSelector('.tlesson, .empty');
      ok((await p.evaluate(() => location.search)).includes('teacher='), T + 'режим преподавателя не включился');
      await p.click('#groupBtn'); await p.click('#whoSeg button[data-who="group"]'); await p.click('#courses button[data-group="11-А"]'); await p.waitForSelector('#list .lesson, #list .empty');
    });

    await step(T + 'история замен', async () => {
      for (let i = 0; i < 3; i++) {
        await openHistory(p); await p.waitForSelector('#historyList details');
        await p.evaluate(() => document.querySelectorAll('#historyList details').forEach((d) => (d.open = true))); await p.waitForTimeout(300);
        const sc = await p.evaluate(() => { const l = document.getElementById('historyList'); l.scrollTop = 400; return l.scrollHeight <= l.clientHeight + 2 || l.scrollTop > 0; });
        ok(sc, T + 'история замен не листается');
        if (i % 2) await p.keyboard.press('Escape'); else await p.click('#history .close');
        await p.waitForTimeout(300);
        ok(!(await p.$('#history[open]')), T + 'история не закрылась');
      }
    });

    if (s.mob) await step(T + 'кнопка «i»', async () => {
      for (const d of ['0', '1']) {
        await tab(p, d); await p.waitForTimeout(600);
        // важная плашка (неуверенно, не прочитано, данные устарели) открыта сразу, обычная — закрыта
        const first = await p.evaluate(() => !document.getElementById('banner').hidden);
        for (let i = 0; i < 4; i++) {
          await p.click('#infoBtn'); await p.waitForTimeout(250);
          const r = await p.evaluate(() => { const i = document.getElementById('infoBtn').getBoundingClientRect(), t = document.querySelector('.tabs').getBoundingClientRect(); const hit = document.elementFromPoint(i.left + i.width / 2, i.top + 4); return { gap: i.top - t.bottom, top: !!hit && !!hit.closest('#infoBtn'), open: !document.getElementById('banner').hidden }; });
          ok(r.gap >= 0 && r.top, T + 'кнопка «i» под вкладками');
          ok(r.open === (i % 2 === 0 ? !first : first), T + 'плашка о заменах не переключается');
        }
      }
      await tab(p, '0');
    });

    await step(T + 'значок интернета', async () => {
      const st = () => p.evaluate(() => document.getElementById('netBtn').className);
      ok((await st()).includes('full'), T + 'значок интернета не «всё хорошо» при хорошей сети');
      await p.route('**/health.json?net=*', async (r) => { await new Promise((x) => setTimeout(x, 2000)); r.continue(); });
      await p.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); await p.waitForTimeout(2600);
      ok((await st()).includes('slow'), T + 'значок не показал медленный интернет');
      await p.unroute('**/health.json?net=*'); await p.route('**/health.json?net=*', (r) => r.abort());
      await p.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); await p.waitForTimeout(800);
      ok((await st()).includes('off'), T + 'значок не показал «нет интернета»');
      await p.click('#netBtn'); await p.waitForTimeout(400);
      ok(await p.isVisible('#netTip'), T + 'пояснение к значку не появилось');
      await p.waitForTimeout(5300); ok(!(await p.isVisible('#netTip')), T + 'пояснение к значку не пропало само');
      await p.unroute('**/health.json?net=*');
      await p.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); await p.waitForTimeout(800);
      ok((await st()).includes('full'), T + 'значок не вернулся в «всё хорошо»');
    });

    await step(T + 'метки отсчёта', async () => {
      const lis = await p.$$('#calendar li');
      for (const li of lis) {
        await li.click(); await p.waitForTimeout(400);
        const r = await p.evaluate(() => { const t = document.getElementById('popTip'); const b = t.getBoundingClientRect(); return { vis: !t.hidden, inside: b.left >= 0 && b.right <= document.documentElement.clientWidth }; });
        ok(r.vis && r.inside, T + 'пояснение к метке не видно или вылезает за экран');
      }
      await p.waitForTimeout(5600); ok(await p.evaluate(() => document.getElementById('popTip').hidden), T + 'пояснение к метке не пропало само');
    });

    await step(T + 'где сейчас преподаватель', async () => {
      await openWhere(p);
      await p.waitForSelector('#whereList button');
      for (let i = 0; i < 3; i++) {
        await p.click('#whereList button'); await p.waitForTimeout(500);
        ok((await p.textContent('#whereOut')).length > 10, T + 'нет ответа «где преподаватель»');
        await p.click('#whereList button[aria-current="true"]'); await p.waitForTimeout(300);
        ok((await p.innerHTML('#whereOut')) === '', T + 'повторное нажатие не убрало ответ');
      }
      await p.fill('#whereInput', 'физ'); await p.waitForTimeout(200);
      const bySubj = await p.$$eval('#whereList button small', (x) => x.map((e) => e.textContent));
      ok(bySubj.length >= 2 && bySubj.every((t) => /физ/i.test(t)), T + 'поиск по предмету «физ» не нашёл преподавателей с предметом');
      await p.fill('#whereInput', 'ззззз'); await p.waitForTimeout(200);
      ok((await p.textContent('#whereList')).includes('Не нашлось'), T + 'нет надписи «не нашлось»');
      await p.fill('#whereInput', 'ё'); await p.fill('#whereInput', '');
      if (await p.$('#panel[open]')) {
        await p.keyboard.press('Escape'); await p.waitForTimeout(300);
        ok(await p.evaluate(() => document.getElementById('whereBox').parentElement.id === 'whereD'), T + 'поиск преподавателя не вернулся на место после окна');
      }
    });

    // плитки разделов (только компьютер): каждая открывает своё окно с содержимым, закрывается крестиком и Esc
    if (!s.mob) await step(T + 'плитки разделов', async () => {
      const tiles = await p.$$eval('#tiles [data-tile]', (x) => x.map((e) => e.dataset.tile));
      ok(tiles.length >= 7, T + 'плиток меньше 7: ' + tiles.join(','));
      ok(await p.evaluate(() => !document.getElementById('whereD').getClientRects().length && !document.getElementById('useful').getClientRects().length),
        T + 'на компьютере видны старые блоки «Где преподаватель» / «Полезное» вместе с плитками');
      for (const [k, t] of tiles.entries()) {
        await p.click('#tiles [data-tile="' + t + '"]'); await p.waitForTimeout(400);
        const r = await p.evaluate(() => { const d = document.querySelector('dialog[open]'); if (!d) return null;
          const b = d.getBoundingClientRect(); return { id: d.id, len: d.innerText.trim().length, inside: b.top >= 0 && b.bottom <= innerHeight && b.left >= 0 && b.right <= innerWidth }; });
        ok(r && r.len > 20, T + 'плитка «' + t + '» не открыла окно с содержимым');
        ok(!r || r.inside, T + 'окно плитки «' + t + '» вылезает за экран');
        if (k % 2) await p.keyboard.press('Escape'); else await p.click('dialog[open] .close');
        await p.waitForTimeout(300);
        ok(!(await p.$('dialog[open]')), T + 'окно плитки «' + t + '» не закрылось');
      }
      await p.click('#tiles [data-tile="bells"]'); await p.waitForTimeout(300);
      ok((await p.$$('#panelBody .p-row')).length >= 10, T + 'в окне «Звонки» нет пар');
      await p.keyboard.press('Escape');
    });

    // полоса дней (и на телефоне): выбранный день виден, нажатие на другой день его выбирает
    await step(T + 'полоса дней', async () => {
      await open(p);
      const sel = await p.evaluate(() => { const n = document.querySelector('.tabs'), b = n.querySelector('.strip[aria-selected="true"]'); if (!b) return null;
        const r = b.getBoundingClientRect(), nr = n.getBoundingClientRect(); return { day: b.dataset.day, inside: r.left >= nr.left - 1 && r.right <= nr.right + 1 }; });
      ok(sel && sel.inside, T + 'в полосе дней не виден выбранный день');
      const other = p.locator('.tabs .strip:not(.wk):not([aria-selected="true"]):not(.past):visible').first();
      const d = await other.getAttribute('data-day'); await other.click(); await p.waitForTimeout(600);
      ok(await p.evaluate((d) => document.querySelector('.tabs .strip[data-day="' + d + '"]').getAttribute('aria-selected') === 'true', d), T + 'нажатие на день в полосе не выбрало его');
      ok(await p.evaluate(() => [...document.querySelectorAll('.tabs > button:not(.strip)')].every((b) => !b.getClientRects().length)), T + 'старые вкладки «Сегодня / Завтра» видны вместе с полосой');
      await open(p);
    });

    // «Поделиться»: картинка дня — в меню «Поделиться» или скачивается
    await step(T + 'поделиться', async () => {
      ok(await p.isVisible('#shareBtn'), T + 'нет надписи «Поделиться»');
      const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 5000 }), p.click('#shareBtn')]);
      ok(/^raspisanie-11-A-\d\d\.\d\d\.png$/.test(dl.suggestedFilename()), T + 'картинка дня скачалась с именем ' + dl.suggestedFilename());
      const size = (await require('fs').promises.stat(await dl.path())).size;
      ok(size > 10000, T + 'картинка дня слишком маленькая: ' + size + ' байт');
    });

    // крупная «следующая пара»: во время пары её нет (видно рамкой «Сейчас»), на компьютере нет вовсе
    await step(T + 'следующая пара крупно', async () => {
      const r = await p.evaluate(() => ({ now: !!document.querySelector('#list .lesson.now'), shown: !document.getElementById('nextUp').hidden }));
      ok(!(r.now && r.shown), T + 'крупная «следующая пара» показана во время пары');
      if (!s.mob) ok(!r.shown, T + 'крупная «следующая пара» на компьютере');
    });

    await step(T + 'змейка', async () => {
      await p.evaluate(() => document.activeElement && document.activeElement.blur());
      if (s.mob) { for (let i = 0; i < 5; i++) await p.tap('.disclaimer'); } else { for (const k of 'wasd') await p.keyboard.press(k); }
      await p.waitForSelector('.snake canvas', { state: 'visible' });
      if (!s.mob) { await p.keyboard.press('ArrowUp'); await p.keyboard.press('ArrowLeft'); }
      await p.waitForTimeout(5000);
      ok((await p.textContent('.snake-hint')).includes('заново'), T + 'змейка не показала проигрыш');
      if (!s.mob) { await p.keyboard.press('Space'); await p.waitForTimeout(300); await p.keyboard.press('Escape'); }
      else await p.click('.snake-close');
      await p.waitForTimeout(300);
      ok(!(await p.isVisible('.snake')), T + 'змейка не закрылась');
    });

    if (s.mob) await step(T + 'свайпы по дням', async () => {
      await tab(p, '0'); await p.waitForTimeout(500);
      const swipe = async (dx, dy = 0) => {
        const t = (x, y) => [{ identifier: 1, clientX: x, clientY: y }];
        await p.dispatchEvent('#list', 'touchstart', { touches: t(200, 600), changedTouches: t(200, 600) });
        await p.dispatchEvent('#list', 'touchend', { touches: [], changedTouches: t(200 + dx, 600 + dy) });
        await p.waitForTimeout(500); return p.$eval('.tabs .strip[aria-selected="true"]', (x) => x.dataset.day);
      };
      // свайп листает дни полосы по порядку (воскресенья в ней нет), в конце — «Неделя»
      const days = await p.$$eval('.tabs .strip', (x) => x.map((e) => e.dataset.day));
      const at = days.indexOf('0');
      ok((await swipe(-150)) === days[at + 1], T + 'свайп влево не перешёл на следующий день');
      ok((await swipe(-150)) === days[at + 2], T + 'второй свайп влево не перешёл дальше');
      ok((await swipe(150)) === days[at + 1], T + 'свайп вправо не вернул предыдущий день');
      ok((await swipe(-60, 300)) === days[at + 1], T + 'вертикальная прокрутка переключила день');
      await tab(p, 'week'); ok((await swipe(-150)) === 'week', T + 'свайп влево после «Недели» что-то переключил');
      await tab(p, '0');
    });

    await step(T + 'тема и подгруппа', async () => {
      const th = () => p.evaluate(() => document.documentElement.dataset.theme || 'авто');
      const seen = new Set(); for (let i = 0; i < 6; i++) { await p.click('#themeBtn'); await p.waitForTimeout(250); seen.add(await th()); }
      ok(seen.size >= 2, T + 'тема не переключается');
      const before = await th(); await p.reload(); await p.waitForSelector('#list .lesson, #list .empty');
      ok((await th()) === before, T + 'тема не запомнилась после перезагрузки');
      if (await p.isVisible('#langSwitch')) {
        const a = await p.isChecked('#langToggle'); await p.click('#langSwitch'); await p.waitForTimeout(500);
        await p.reload(); await p.waitForSelector('#list .lesson, #list .empty');
        ok((await p.isChecked('#langToggle')) !== a, T + 'подгруппа не запомнилась');
        await p.click('#langSwitch');
      }
    });

    await step(T + 'неправильные адреса', async () => {
      for (const q of ['?group=99-Я', '?group=', '?date=2026-13-45&group=11-%D0%90', '?teacher=%D0%9D%D0%B5%D1%82%D0%B0%D0%BA%D0%BE%D0%B9', '?group=<script>', '?date=1999-01-01&group=11-%D0%90']) {
        await p.goto(URL + q); await p.waitForTimeout(1800);
        const r = await p.evaluate(() => ({ body: document.body.innerText.length, script: !!document.querySelector('body script:not([src])') && document.body.innerHTML.includes('<script>alert') }));
        ok(r.body > 50, T + 'пустая страница по адресу ' + q);
        await p.keyboard.press('Escape');
      }
    });

    P.push(...p.errs.map((x) => T + x)); await p.ctx.close();
  }

  // счётчик: раз в день, автопроверки не считаются
  await (async () => {
    const ctx = await b.newContext({ viewport: { width: 393, height: 800 } }); const hits = [];
    await ctx.route('**/macros/s/**', (r) => { hits.push(r.request().url()); r.fulfill({ status: 200, body: 'ok' }); });
    const p = await ctx.newPage(); await p.addInitScript(() => Object.defineProperty(navigator, 'webdriver', { get: () => false }));
    for (let i = 0; i < 3; i++) { await p.goto(URL + '?group=11-%D0%90'); await p.waitForTimeout(5200); }
    ok(hits.length === 1, 'счётчик: за 3 открытия ' + hits.length + ' отметок вместо 1');
    await ctx.close();
    const c2 = await b.newContext(); let h2 = 0; await c2.route('**/macros/s/**', (r) => { h2++; r.fulfill({ status: 200, body: 'ok' }); });
    const q = await c2.newPage(); await q.goto(URL + '?group=11-%D0%90'); await q.waitForTimeout(5200);
    ok(h2 === 0, 'счётчик считает автопроверки'); await c2.close();
  })().catch((e) => P.push('счётчик: не удалось — ' + e.message));

  // часы: после смены минуты новая цифра того же размера, что и остальные (на телефоне и компьютере, обе темы)
  for (const s of [{ w: 393, mob: true }, { w: 1366, mob: false }, { w: 1920, mob: false, dark: true }]) {
    await (async () => {
      const p = await page(b, { w: s.w, h: 800, mob: s.mob, dark: s.dark });
      await open(p);
      for (let m = 0; m < 3; m++) {
        await p.clock.runFor(60000); await p.waitForTimeout(400);
        const sizes = await p.evaluate(() => {
          const c = document.getElementById('clock');
          return [c, ...c.querySelectorAll('span')].map((el) => getComputedStyle(el).fontSize);
        });
        ok(new Set(sizes).size === 1, s.w + 'px часы: после смены минуты цифры разного размера (' + [...new Set(sizes)].join(', ') + ')');
      }
      await p.ctx.close();
    })().catch((e) => P.push(s.w + 'px часы: не удалось — ' + e.message));
  }

  await b.close();
  report('Функции сайта', P);
})();
