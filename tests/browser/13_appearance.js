const assert = require('node:assert/strict');
const { URL, launch, page, report } = require('./lib');
(async () => {
  const browser = await launch();
  const problems = [];
  try {
    for (const mode of ['weather', 'season', 'manual']) {
      const p = await page(browser);
      try {
        await p.addInitScript(mode => {
          localStorage.setItem('utgt-appearance-v1', JSON.stringify({mode, manual:'rain', intensity:100, holidays:true}));
          localStorage.setItem('utgt-ukhta-weather-v1', '{}');
        }, mode);
        await p.goto(URL + '?group=' + encodeURIComponent('11-А'));
        await p.waitForSelector('#list .lesson, #list .empty');
        assert.equal(await p.locator('#appearanceBtn, #appearanceDialog, .appearance-layer').count(), 0);
        assert.equal(await p.locator('script[src*="appearance"], link[href*="appearance"]').count(), 0);
        assert.equal(await p.evaluate(() => localStorage.getItem('utgt-appearance-v1')), null);
        assert.equal(await p.evaluate(() => localStorage.getItem('utgt-ukhta-weather-v1')), null);
        problems.push(...p.errs);
      } catch (error) { problems.push(mode + ': ' + error.message); }
      finally { await p.ctx.close(); }
    }
  } finally { await browser.close(); }
  report('Retired appearance settings', problems);
  if (problems.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
