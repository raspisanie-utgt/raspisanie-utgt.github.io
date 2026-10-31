// Данные на экране совпадают с расчётом: все группы × все дни с заменами, неделя после последней замены,
// начала каникул/практик/сессий и праздники. Обе языковые подгруппы. Проверяет и плашку, и число замен.
const { read, URL, groups, zdays, launch, page, report, ROOT } = require('./lib');
const A = require(ROOT + '/site/agenda.js'), C = require(ROOT + '/site/calendar.js');
const bells = read('data/bells.json'), cal = read('data/calendar.json'), ix = read('data/groups/index.json').groups;
const VALID_TO = read('data/groups/index.json').valid_to;
const zam = (d) => (zdays().includes(d) ? read('data/zameny/' + d + '.json') : null);
const forGroup = (z, g) => (z ? Object.assign({}, z, { changes: z.all_changes ? z.all_changes[g] || [] : [] }) : null);
const SH = { 'Основы безопасности и защиты Родины': 'ОБЗР', 'Безопасность жизнедеятельности': 'БЖД' };
const nice = (x) => x.split(' / ').map((y) => SH[y.trim()] || y.trim().replace(/Иностранный язык \((\S+)\)/, (m, l) => l[0].toUpperCase() + l.slice(1) + ' язык').replace(/\s*\(по видам[^)]*\)\s*$/, '')).join(' / ');
const addDays = (d, n) => new Date(Date.parse(d) + n * 864e5).toISOString().slice(0, 10);

(async () => {
  const days = new Set(zdays());
  for (let i = 1; i <= 8; i++) days.add(addDays(zdays().slice(-1)[0], i));
  (cal.holidays || []).forEach((h) => days.add(h.date));
  const problems = [];
  const b = await launch();
  let checked = 0;
  for (const lang of ['английский', 'немецкий']) {
    const p = await page(b, { now: false });
    await p.goto(URL); await p.evaluate((l) => localStorage.setItem('utgt-lang', l), lang);
    for (const g of ix) {
      const sched = read('data/groups/' + g.file);
      const gd = new Set(days);
      (cal.groups[g.group].periods || []).forEach((x) => { gd.add(x.from); gd.add(addDays(x.to, 1)); });
      for (const d of [...gd].sort()) {
        if (d < '2026-09-01' || d > '2027-07-10') continue;
        const z = forGroup(zam(d), g.group);
        // как на сайте: в каникулы и на практике — только строки замен; после valid_to — ничего (нового расписания нет)
        const off = C.dayOff(d, cal, g.group);
        let ag = A.forLanguage(A.build(d, off ? Object.assign({}, sched, { days: {} }) : sched, bells, z), lang);
        if ((off && !(z && z.changes.length)) || (VALID_TO && d > VALID_TO)) ag.items = [];
        const exp = ag.items.map((it) => it.startText + ' ' + nice(it.subject) + ' ' + (it.room || ''));
        await p.goto(URL + '?group=' + encodeURIComponent(g.group) + '&date=' + d);
        await p.waitForFunction(() => document.querySelector('#list .lesson, #list .empty') && (document.getElementById('groupName').dataset.typed || document.getElementById('groupName').textContent) !== 'Группа', null, { timeout: 15000 }).catch(() => problems.push(`${g.group} ${d}: страница не открылась`));
        const got = await p.$$eval('#list .lesson', (els) => els.map((e) => e.querySelector('.time').firstChild.textContent + ' ' + e.querySelector('.subj').innerText.replace(/\n/g, ' / ').replace(/(идёт|далее|замена|\?).*$/, '').trim() + ' ' + e.querySelector('.room').textContent.replace('ауд. ', '')));
        const changed = await p.$$eval('#list .lesson.changed', (x) => x.length);
        const expChanged = ag.items.filter((i) => i.changed).length;
        const norm = (s) => s.replace(/\s+/g, ' ').trim();
        const same = exp.length === got.length && exp.every((e, i) => norm(got[i]).startsWith(norm(e).split(' ').slice(0, 2).join(' ')));
        checked++;
        if (!same || changed !== expChanged) problems.push(`${g.group} ${d} (${lang}): ожидалось ${exp.length} пар (${expChanged} замен), на экране ${got.length} (${changed}) | ожид: ${exp.join(' ; ')} | экран: ${got.join(' ; ')}`);
      }
    }
    problems.push(...p.errs);
    await p.ctx.close();
  }
  await b.close();
  console.log('проверено страниц:', checked);
  report('Данные групп на экране', problems);
})();
