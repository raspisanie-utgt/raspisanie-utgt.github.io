const assert = require('node:assert/strict');
const { URL, read, lastZ, launch, report } = require('./lib');

const date = lastZ();
const order = read('data/zameny/' + date + '.json');
const group = order.all_changes['11-А'] ? '11-А' : Object.keys(order.all_changes)[0];
const previous = new Date(Date.parse(date + 'T10:00:00+03:00') - 86400000);

(async () => {
  const browser = await launch();
  const problems = [];
  try {
    for (const width of [1366, 393]) {
      const context = await browser.newContext({
        viewport: { width, height: 840 }, isMobile: width < 500,
        hasTouch: width < 500, serviceWorkers: 'block',
      });
      const page = await context.newPage();
      let published = false;
      let freshIndexRequests = 0;
      let corrected = false;
      let orderStatus = 200;
      let indexed = true;
      let savedIndex = false;
      try {
        await page.clock.setFixedTime(previous);
        await page.route('**/data/zameny/index.json', async route => {
          if (published) freshIndexRequests++;
          if (published && indexed) return route.continue();
          const index = read('data/zameny/index.json');
          index.days = index.days.filter(day => day !== date);
          await route.fulfill({ json: index, headers: savedIndex ? { 'X-Utgt-Saved': '1' } : {} });
        });
        const correctedFile = order.images[0].file + '?review=2';
        await page.route('**/data/zameny/' + date + '.json', route => {
          if (orderStatus !== 200) return route.fulfill({ status: orderStatus });
          if (!corrected) return route.continue();
          const images = [{ ...order.images[0], file: correctedFile }, ...order.images.slice(1)];
          return route.fulfill({ json: { ...order, images } });
        });
        await page.goto(URL + '?group=' + encodeURIComponent(group));
        await page.locator('#list .lesson, #list .empty').first().waitFor();
        const tomorrow = page.locator('.tabs button[data-day="1"]:visible').first();
        const photo = page.locator('#imageList a[href="data/zameny/' + order.images[0].file + '"]');
        assert.equal(await photo.count(), 0);
        published = true;
        await tomorrow.click();
        await photo.waitFor({ timeout: 5000 });
        assert.ok(freshIndexRequests > 0);
        await page.locator('.tabs button[data-day="0"]:visible').first().click();
        corrected = true;
        await page.clock.setFixedTime(new Date(previous.getTime() + 31000));
        await tomorrow.click();
        await page.locator('#imageList a[href="data/zameny/' + correctedFile + '"]').waitFor({ timeout: 5000 });
        const correctedPhoto = page.locator('#imageList a[href="data/zameny/' + correctedFile + '"]');
        const today = page.locator('.tabs button[data-day="0"]:visible').first();
        async function revisit(ms, expectedRequest) {
          await today.click();
          await page.clock.setFixedTime(new Date(previous.getTime() + ms));
          const response = page.waitForResponse(expectedRequest, { timeout: 5000 });
          await tomorrow.click();
          await response;
        }
        const indexResponse = response => response.url().endsWith('/data/zameny/index.json');
        const orderResponse = response => response.url().endsWith('/data/zameny/' + date + '.json');
        orderStatus = 503;
        await revisit(62000, orderResponse);
        await correctedPhoto.waitFor({ timeout: 5000 });
        orderStatus = 404;
        await revisit(93000, indexResponse);
        await correctedPhoto.waitFor({ timeout: 5000 });
        indexed = false;
        savedIndex = true;
        await revisit(124000, indexResponse);
        await correctedPhoto.waitFor({ timeout: 5000 });
        savedIndex = false;
        await revisit(155000, indexResponse);
        await correctedPhoto.waitFor({ state: 'detached', timeout: 5000 });
        indexed = true;
        orderStatus = 200;
        await revisit(186000, indexResponse);
        await correctedPhoto.waitFor({ timeout: 5000 });
        await page.reload();
        await tomorrow.click();
        await page.locator('#imageList a[href="data/zameny/' + correctedFile + '"]').waitFor({ timeout: 5000 });
      } catch (error) {
        problems.push(width + 'px: ' + String(error).split('\n')[0]);
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  report('Substitutions published, corrected, withdrawn, and restored in an open tab', problems);
  if (problems.length) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
