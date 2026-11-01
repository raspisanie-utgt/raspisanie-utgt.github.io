// Расписание каждого преподавателя на экране совпадает с расчётом по всем группам и заменам
const { read, URL, zdays, launch, page, report, ROOT } = require('./lib');
const T = require(ROOT + '/site/teachers.js');
const ix = read('data/groups/index.json').groups, bells = read('data/bells.json'), cal = read('data/calendar.json');
// «Разговоры о важном» ведёт куратор группы (data/info.json) — как на сайте
const cur = (read('data/info.json') || {}).curators || {};
const sch = ix.map((g) => ({ group: g.group, schedule: read('data/groups/' + g.file), curator: cur[g.group] || '' }));
const zf = (d) => { const z = zdays().includes(d) ? read('data/zameny/' + d + '.json') : null; return (g) => (z ? Object.assign({}, z, { changes: (z.all_changes || {})[g] || [] }) : null); };
(async () => {
  const days = zdays().slice(-3).concat((cal.holidays || []).map((h) => h.date).filter((d) => d > zdays().slice(-1)[0]).slice(0, 1));
  const b = await launch(); const p = await page(b, { now: false }); const problems = []; let n = 0;
  for (const t of T.list(sch)) for (const d of days) {
    const exp = T.day(t, d, sch, bells, cal, zf(d)).items.map((x) => x.startText + ' ' + x.groups.join(', '));
    await p.goto(URL + '?teacher=' + encodeURIComponent(t) + '&date=' + d);
    await p.waitForFunction(() => document.querySelector('.tlesson, .empty') && (document.getElementById('groupName').dataset.typed || document.getElementById('groupName').textContent) !== 'Группа', null, { timeout: 15000 }).catch(() => problems.push(`${t} ${d}: страница не открылась`));
    const got = await p.$$eval('.tlesson', (e) => e.map((x) => x.querySelector('.time').firstChild.textContent + ' ' + x.querySelector('.groups').textContent));
    n++;
    if (JSON.stringify(exp) !== JSON.stringify(got)) problems.push(`${t} ${d}: ожид ${exp.join('; ')} | экран ${got.join('; ')}`);
  }
  problems.push(...p.errs); await b.close();
  console.log('страниц преподавателей:', n);
  report('Расписания преподавателей', problems);
})();
