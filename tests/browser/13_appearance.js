const assert = require('node:assert/strict');
const { URL, launch, page, report } = require('./lib');

const sizes = [[360, 780], [412, 915], [2560, 1080], [3440, 1440]];
const snowColor = '#c5e1ff';

async function probe(browser, w, h) {
  const p = await page(browser, { w, h, mob: w < 700, dark: w === 412 || w === 2560 });
  const problems = [];
  try {
    await p.addInitScript(color => {
      window.appearanceProbe = { frames: 0, shedding: 0, snow: 0, rain: 0 };
      const count = (method, key, paint) => {
        const original = CanvasRenderingContext2D.prototype[method];
        CanvasRenderingContext2D.prototype[method] = function (...args) {
          if (this.canvas.classList.contains('appearance-layer') && (!paint || this.fillStyle === paint)) window.appearanceProbe[key]++;
          return original.apply(this, args);
        };
      };
      count('clearRect', 'frames');
      count('arc', 'shedding', color);
      count('fill', 'snow', '#dcecff');
      count('stroke', 'rain');
    }, snowColor);
    let weatherCalls = 0;
    await p.route('https://api.open-meteo.com/**', route => {
      weatherCalls++;
      return route.fulfill({ json: { current: { weather_code: 63, is_day: 1, wind_speed_10m: 8 } } });
    });
    await p.goto(URL + '?group=' + encodeURIComponent('11-А'));
    await p.locator('#list .lesson').first().waitFor();
    const layer = p.locator('.appearance-layer');
    const settings = p.locator('#appearanceBtn');
    const dialog = p.locator('#appearanceDialog');
    const mode = dialog.locator('[name="mode"]');
    const close = () => dialog.getByRole('button', { name: 'Закрыть' }).click();
    const counts = () => p.evaluate(() => ({ ...window.appearanceProbe }));
    const control = dialog.locator('[name="intensity"]');
    const theme = await p.locator('html').getAttribute('data-theme');
    const lesson = p.locator('#list .lesson').first();
    const size = () => lesson.evaluate(el => [el.offsetWidth, el.offsetHeight]);
    const initialSize = await size();
    await settings.click();
    assert.equal(await mode.evaluate(el => el.value), 'off');
    assert.equal(await layer.count(), 0);
    assert.equal(weatherCalls, 0);
    await mode.selectOption('manual');
    await dialog.locator('[name="manual"]').selectOption('snow');
    await control.press('End');
    assert.equal(await dialog.locator('output').innerText(), '100%');
    const bounds = await dialog.evaluate(el => {
      const r = el.getBoundingClientRect();
      return [r.left, r.top, r.right, r.bottom, document.documentElement.clientWidth, innerHeight];
    });
    assert.ok(bounds[0] >= -1 && bounds[1] >= -1 && bounds[2] <= bounds[4] + 1 && bounds[3] <= bounds[5] + 1);
    await close();
    await layer.waitFor();
    assert.equal(await layer.evaluate(el => getComputedStyle(el).pointerEvents), 'none');
    assert.ok(await layer.evaluate(el => el.width * el.height <= 1600000));
    assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1));
    assert.deepEqual(await size(), initialSize, 'decorations do not resize schedule cards');
    const before = await counts();
    await p.clock.runFor(1000);
    const after = await counts();
    assert.ok(after.frames > before.frames && after.frames - before.frames <= 37, 'frame rate is bounded');

    // Advance the page clock to grow a visible pile without a slow real-time wait.
    await lesson.evaluate(el => el.scrollIntoView({ block: 'center' }));
    await p.clock.runFor(5000);
    assert.ok((await counts()).snow > 0, 'snow on card edges');
    await lesson.click();
    await p.clock.runFor(300);
    assert.ok((await counts()).shedding > 0, 'click sheds accumulated snow');
    if (w === 360) {
      const summary = p.locator('#useful summary');
      // Focus a visible summary and let the intersection observer register its edge.
      await summary.evaluate(el => el.scrollIntoView({ block: 'center' }));
      await p.clock.runFor(1200);
      const previous = (await counts()).shedding;
      await summary.click();
      await p.clock.runFor(350);
      assert.ok((await counts()).shedding > previous, 'expanding a panel sheds snow');
    }

    await p.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, value: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const paused = (await counts()).frames;
    await p.clock.runFor(400);
    assert.equal((await counts()).frames, paused, 'hidden tabs stop drawing');
    await p.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await p.clock.runFor(200);
    assert.ok((await counts()).frames > paused);
    await p.emulateMedia({ reducedMotion: 'reduce' });
    await p.clock.runFor(150);
    assert.equal(await layer.count(), 0, 'reduced motion suppresses snowfall');
    await p.emulateMedia({ reducedMotion: 'no-preference' });
    await p.reload();
    await settings.click();
    assert.equal(await mode.evaluate(el => el.value), 'manual');
    assert.equal(await control.evaluate(el => el.value), '100');
    assert.equal(await p.locator('html').getAttribute('data-theme'), theme);
    await mode.selectOption('weather');
    await close();
    await p.waitForFunction(() => window.appearanceProbe.rain > 0);
    assert.equal(weatherCalls, 1);
    await p.ctx.setOffline(true);
    await p.clock.runFor(100);
    const rainBefore = (await counts()).rain;
    await p.clock.runFor(150);
    assert.equal((await counts()).rain, rainBefore, 'offline switches to seasonal effects');
    await p.ctx.setOffline(false);
    await settings.click();
    await mode.selectOption('off');
    await close();
    assert.equal(await layer.count(), 0);
    assert.equal(weatherCalls, 1);
    problems.push(...p.errs);
  } finally { await p.ctx.close(); }
  return problems;
}

(async () => {
  const browser = await launch();
  const problems = [];
  try {
    for (const [w, h] of sizes) {
      try { problems.push(...(await probe(browser, w, h)).map(problem => `${w}×${h}: ${problem}`)); }
      catch (error) { problems.push(`${w}×${h}: ${error.stack || error}`); }
    }
  } finally { await browser.close(); }
  report('Appearance effects', problems);
  if (problems.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
