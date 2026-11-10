// Регрессии из браузерного аудита 10.11.2026: ошибки загрузки, перекрытие шапки,
// архив, фото и доступность. Подмена HTTP 503 действует только в тестовом браузере.
const { URL, SHOTS, lastZ, launch, report } = require('./lib');
const path = require('path');

const group = '11-А';
const date = lastZ();
const query = '?group=' + encodeURIComponent(group) + '&date=' + date;
const problems = [];

async function check(browser, name, options, body) {
  const ctx = await browser.newContext({
    viewport: { width: options.width || 390, height: options.height || 844 },
    serviceWorkers: 'block', locale: 'ru-RU',
    reducedMotion: options.reducedMotion ? 'reduce' : 'no-preference',
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error).split('\n')[0]));
  try {
    if (options.fail) {
      await page.route('**/*', async (route) => {
        const pathname = new globalThis.URL(route.request().url()).pathname;
        if (options.fail(pathname))
          await route.fulfill({ status: 503, contentType: 'text/plain', body: 'simulated 503' });
        else await route.continue();
      });
    }
    await page.goto(URL + query, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(1800);
    const found = await body(page, errors);
    if (found) {
      problems.push(name + ': ' + found);
      await page.screenshot({ path: path.join(SHOTS, '11_' + name + '.png'), fullPage: true }).catch(() => {});
    }
  } catch (error) {
    problems.push(name + ': тест не завершён: ' + String(error).split('\n')[0]);
    await page.screenshot({ path: path.join(SHOTS, '11_' + name + '.png'), fullPage: true }).catch(() => {});
  } finally {
    await ctx.close();
  }
}

(async () => {
  const browser = await launch();
  try {
    // HTTP 503 списка замен не должен превращаться в утверждение «замен нет».
    await check(browser, 'index-503', { fail: p => p.endsWith('/data/zameny/index.json') }, async (page) => {
      const banner = page.locator('#banner');
      const info = page.locator('#infoBtn');
      if (await info.isVisible()) await info.click().catch(() => {});
      const claim = (await banner.innerText()).includes('Замен на этот день пока нет');
      return claim ? 'HTTP 503 подменяет ошибку сообщением об отсутствии замен' : null;
    });

    // Сбой загрузки группы не должен оставлять вечный скелетон и исключение JS.
    const lookup = await browser.newContext();
    const index = await lookup.request.get(URL + 'data/groups/index.json');
    const entries = (await index.json()).groups || [];
    await lookup.close();
    const file = entries.find(x => x.group === group)?.file;
    if (!file) problems.push('group-503: не найден файл группы ' + group);
    else await check(browser, 'group-503', { fail: p => p.endsWith('/data/groups/' + file) }, async (page, errors) => {
      const busy = await page.locator('#list').getAttribute('aria-busy');
      const bodyText = await page.locator('body').innerText();
      const visibleError = /не удалось загрузить|ошибк.*расписан|повторить|попробуйте ещё/i.test(bodyText);
      if (errors.length) return 'ошибка JavaScript: ' + errors[0];
      if (busy === 'true') return 'после HTTP 503 осталась вечная загрузка';
      if (!visibleError) return 'нет заметного сообщения о сбое загрузки группы';
      return null;
    });

    // Элемент поверх кнопки темы не должен перехватывать нажатие.
    await check(browser, 'theme-1440', { width: 1440, height: 900 }, async (page) => {
      const button = page.locator('#themeBtn');
      if (!await button.isVisible()) return 'кнопка темы не видна';
      const box = await button.boundingBox();
      if (!box) return 'не удалось измерить кнопку темы';
      const hit = await page.evaluate(([x, y]) => {
        const element = document.elementFromPoint(x, y);
        return !!(element && (element.id === 'themeBtn' || element.closest('#themeBtn')));
      }, [box.x + box.width / 2, box.y + box.height / 2]);
      return hit ? null : 'центр кнопки темы перекрыт другим элементом';
    });

    // Последний опубликованный день должен присутствовать в истории.
    await check(browser, 'archive', {}, async (page) => {
      const result = await page.request.get(URL + 'data/history/all.json');
      if (!result.ok()) return 'история недоступна, HTTP ' + result.status();
      const dates = (await result.json()).days.map(x => x.date);
      return dates.includes(date) ? null : 'последний день ' + date + ' отсутствует в истории';
    });

    // При недоступном оригинале не показывать только сломанную картинку.
    await check(browser, 'photo-503', {
      fail: p => /\/data\/zameny\/\d{4}-\d{2}-\d{2}-\d+\.jpe?g$/.test(p),
    }, async (page) => {
      const preview = page.locator('#imageList img').first();
      if (!await preview.count()) return 'нет превью изображения для дня ' + date;
      await preview.click();
      await page.waitForTimeout(600);
      const viewer = page.locator('#viewer');
      if (!await viewer.isVisible()) return 'просмотрщик не открылся';
      const broken = await page.locator('#viewerImg').evaluate(im => im.complete && im.naturalWidth === 0);
      const message = await viewer.innerText();
      return broken && !/ошиб|недоступ|повтор|не удалось/i.test(message)
        ? 'оригинал недоступен, но показана только сломанная картинка' : null;
    });

    // Стрелки должны перемещать фокус по ARIA-вкладкам дат.
    await check(browser, 'keyboard-tabs', { width: 1440, height: 900 }, async (page) => {
      const tabs = page.locator('.tabs [role="tab"]');
      if (await tabs.count() < 2) return 'не найдены вкладки дат';
      await tabs.first().focus();
      await page.keyboard.press('ArrowRight');
      const changed = await page.evaluate(() => document.activeElement !== document.querySelector('.tabs [role="tab"]'));
      return changed ? null : 'ArrowRight не перемещает фокус между вкладками';
    });
  } finally {
    await browser.close();
  }
  report('Регрессии аудита: HTTP 503, шапка, история, фото и клавиатура', problems);
})().catch(err => {
  console.log('  - аудит прервался: ' + String(err).split('\n')[0]);
  console.log('ИТОГ: проблем 1');
  process.exitCode = 1;
});
