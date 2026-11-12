const assert = require('node:assert/strict');
const { URL, NOW, launch, page, read, report } = require('./lib');

async function probe(browser, width) {
  const group = '21-С';
  const source = read('data/groups/21s.json');
  const known = structuredClone(source);
  for (const rows of Object.values(known.days)) {
    for (const row of rows) if (!row.room || row.room.includes('?')) row.room = '1-25';
  }
  const schedule = structuredClone(known);
  schedule.verified = true;
  schedule.days[5] = [{ lessons: [3, 4], subject: 'Математика', room: '?' },
    { lessons: [5, 6], subject: 'Физика', room: '2-?' }];
  const p = await page(browser, { w: width, h: width < 700 ? 780 : 900, mob: width < 700 });
  let verified = false;
  const readGroup = route => route.fulfill({ json: verified ? known : schedule });
  const location = URL + '?group=' + encodeURIComponent(group);
  const postRequests = [];
  const watch = tab => tab.on('request', request => { if (request.method() !== 'GET') postRequests.push(request.method()); });
  try {
    watch(p);
    await p.route('**/data/groups/21s.json', readGroup);
    await p.goto(location);
    await p.locator('#list .lesson, #list .empty').first().waitFor();
    const panel = p.locator('#roomSurvey');
    const open = () => panel.getByRole('button', { name: 'Показать вопросы' }).click();
    const submit = panel.getByRole('button', { name: 'Отправить' });
    await open();
    const inputs = panel.locator('input');
    assert.equal(await inputs.count(), 2);
    const first = inputs.first();
    await first.fill('name@example.com');
    assert.equal(await first.getAttribute('aria-invalid'), 'true');
    await first.fill('1-25');
    assert.equal(await first.getAttribute('aria-invalid'), 'false');
    assert.equal(await inputs.last().inputValue(), '');
    assert.equal(await submit.isEnabled(), false);
    await first.press('Enter');
    await first.press('Enter');
    assert.equal(postRequests.length, 0);
    assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1));
    await p.locator('.tabs button[data-day="week"]:visible').first().click();
    await p.locator('#weekView').waitFor();
    await panel.getByRole('button', { name: 'Пропустить' }).click();
    await panel.waitFor({ state: 'hidden' });
    await p.reload();
    await p.locator('#list .lesson, #list .empty').first().waitFor();
    assert.equal(await panel.isVisible(), false);

    const newTab = await p.ctx.newPage();
    await newTab.clock.setFixedTime(NOW());
    watch(newTab);
    await newTab.route('**/data/groups/21s.json', readGroup);
    await newTab.goto(location);
    const nextPanel = newTab.locator('#roomSurvey');
    await nextPanel.getByRole('button', { name: 'Показать вопросы' }).click();
    verified = true;
    await newTab.reload();
    await newTab.locator('#list .lesson, #list .empty').first().waitFor();
    assert.equal(await nextPanel.isVisible(), false, 'known classroom removes the question');
    verified = false;
    await newTab.reload();
    await nextPanel.getByRole('button', { name: 'Показать вопросы' }).click();
    await nextPanel.getByRole('button', { name: 'Больше не показывать' }).click();
    await nextPanel.waitFor({ state: 'hidden' });
    const lastTab = await p.ctx.newPage();
    await lastTab.clock.setFixedTime(NOW());
    await lastTab.route('**/data/groups/21s.json', readGroup);
    await lastTab.goto(location);
    await lastTab.locator('#list .lesson, #list .empty').first().waitFor();
    assert.equal(await lastTab.locator('#roomSurvey').isVisible(), false);
    assert.equal(await lastTab.evaluate(() => localStorage.getItem('utgt-room-survey-never')), '1');
    assert.equal(postRequests.length, 0);
    return p.errs;
  } finally { await p.ctx.close(); }
}

(async () => {
  const browser = await launch();
  const problems = [];
  try {
    for (const width of [360, 1366]) {
      try { problems.push(...(await probe(browser, width)).map(problem => `${width}px: ${problem}`)); }
      catch (error) { problems.push(`${width}px: ${error.stack || error}`); }
    }
  } finally { await browser.close(); }
  report('Classroom questionnaire preview', problems);
  if (problems.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
