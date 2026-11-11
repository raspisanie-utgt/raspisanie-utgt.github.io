// Регрессии из браузерного аудита 10.11.2026: ошибки загрузки, перекрытие шапки,
// архив, фото и доступность. Подмена HTTP 503 действует только в тестовом браузере.
const { URL, SHOTS, lastZ, launch, report } = require('./lib');
const path = require('path');

const group = '11-А';
const date = lastZ();
const query = '?group=' + encodeURIComponent(group) + '&date=' + date;
const readyDay = '#list .lesson, #list .empty:not(:has(.retry-data))';
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
        const failure = options.fail(pathname);
        if (failure === 'offline') await route.abort('internetdisconnected');
        else if (failure === 'saved') {
          const response = await route.fetch();
          await route.fulfill({ response, headers: { ...response.headers(), 'X-Utgt-Saved': '1' } });
        }
        else if (failure)
          await route.fulfill({ status: failure === true ? 503 : failure, contentType: 'text/plain', body: 'simulated failure' });
        else await route.continue();
      });
    }
    await page.goto(URL + (options.query || query), { waitUntil: 'domcontentloaded', timeout: 30000 });
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
    else {
      let failing = true;
      const groupFile = '/data/groups/' + file;
      await check(browser, 'group-503', { fail: p => failing && p.endsWith(groupFile) }, async (page, errors) => {
        const list = page.locator('#list');
        const retry = list.getByRole('button', { name: 'Повторить' });
        if (await list.getAttribute('aria-busy') === 'true') return 'после HTTP 503 осталась вечная загрузка';
        if (!await list.getByRole('alert').isVisible() || !await retry.isVisible())
          return 'нет предупреждения и кнопки в расписании';
        if ((await retry.boundingBox()).height < 44) return 'кнопка повтора слишком мала для телефона';
        await page.locator('.tabs button[data-day="week"]:visible').first().click();
        const weekRetry = page.locator('#weekView').getByRole('button', { name: 'Повторить' });
        await weekRetry.waitFor({ timeout: 5000 });
        failing = false;
        await weekRetry.click();
        await weekRetry.waitFor({ state: 'hidden', timeout: 7000 });
        await page.locator('.tabs button[data-day="0"]:visible').first().click();
        await page.locator(readyDay).first().waitFor({ timeout: 7000 });
        await page.locator('#groupBtn').click();
        await page.locator('#courses button[data-group="21-С"]').click();
        await page.waitForURL(/group=21-/);
        await page.waitForFunction(() => document.title.endsWith('21-С'), null, { timeout: 7000 });
        await page.locator(readyDay).first().waitFor({ timeout: 7000 });
        return errors.length ? 'ошибка JavaScript: ' + errors[0] : null;
      });
      failing = true;
      await check(browser, 'teacher-404', {
        query: '?teacher=' + encodeURIComponent('Трудова С.В.') + '&date=2026-10-27',
        fail: p => failing && p.endsWith(groupFile) ? 404 : false,
      }, async (page, errors) => {
        const retry = page.locator('#list').getByRole('button', { name: 'Повторить' });
        await retry.waitFor({ timeout: 5000 });
        failing = false;
        await retry.click();
        await page.locator('#list .tlesson').first().waitFor({ timeout: 8000 });
        return errors.length ? 'ошибка JavaScript: ' + errors[0] : null;
      });
      failing = true;
      await check(browser, 'offline-first-load', {
        fail: p => failing && p.endsWith('/data/groups/index.json') ? 'offline' : false,
      }, async (page, errors) => {
        await page.locator('#list').getByRole('button', { name: 'Повторить' }).waitFor({ timeout: 5000 });
        await page.context().setOffline(true);
        failing = false;
        await page.context().setOffline(false);
        await page.locator(readyDay).first().waitFor({ timeout: 8000 });
        return errors.length ? 'ошибка JavaScript: ' + errors[0] : null;
      });
      let groupRequests = 0;
      await check(browser, 'saved-group-refresh', {
        fail: p => p.endsWith(groupFile) && ++groupRequests === 1 ? 'saved' : false,
      }, async (page, errors) => {
        const button = page.locator('#netBtn');
        if (!/сохран[её]н/i.test(await button.getAttribute('aria-label')))
          return 'сохранённая копия показана без пометки';
        await page.context().setOffline(true);
        await page.context().setOffline(false);
        await page.waitForFunction(() => !/сохран[её]н/i.test(document.getElementById('netBtn').getAttribute('aria-label')), null, { timeout: 8000 });
        if (groupRequests < 2) return 'пометка исчезла до повторной загрузки расписания';
        return errors.length ? 'ошибка JavaScript: ' + errors[0] : null;
      });
      let pickerFails = true;
      await check(browser, 'teacher-picker-503', {
        fail: p => pickerFails && p.endsWith('/data/groups/21s.json'),
      }, async (page, errors) => {
        await page.locator('#groupBtn').click();
        await page.locator('#whoSeg button[data-who="teacher"]').click();
        const retry = page.locator('#teacherList').getByRole('button', { name: 'Повторить' });
        await retry.waitFor({ timeout: 6000 });
        pickerFails = false;
        await retry.click();
        await page.locator('#teacherList button[data-teacher]').first().waitFor({ timeout: 8000 });
        return errors.length ? 'ошибка JavaScript: ' + errors[0] : null;
      });
    }

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
      fail: p => /\/data\/zameny\/\d{4}-\d{2}-\d{2}-\d+\.(?:png|jpe?g)$/i.test(p),
    }, async (page) => {
      const preview = page.locator('#imageList img').first();
      if (!await preview.count()) return 'нет превью изображения для дня ' + date;
      await preview.click();
      const viewer = page.locator('#viewer');
      if (!await viewer.isVisible()) return 'просмотрщик не открылся';
      await viewer.getByText(/не удалось|недоступ/i).first().waitFor({ timeout: 5000 });
      return null;
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

    await check(browser, 'keyboard-teacher-search', { width: 1366, height: 900 }, async (page) => {
      await page.locator('#tiles [data-tile="where"]').click();
      const panel = page.locator('#panel');
      await panel.locator('#whereInput').fill('рыж');
      await page.keyboard.press('Escape');
      await panel.waitFor({ state: 'hidden', timeout: 5000 });
      return null;
    });

    await check(browser, 'reduced-motion', { reducedMotion: true }, async (page, errors) => {
      await page.locator('#groupBtn').click();
      const active = await page.locator('#picker').evaluate(dialog => dialog.getAnimations({ subtree: true }).length);
      if (active) return 'диалог проигрывает анимацию при включённом уменьшении движения';
      await page.keyboard.press('Escape');
      if (await page.locator('#picker').isVisible()) return 'Escape не закрыл диалог выбора';
      return errors.length ? 'ошибка JavaScript: ' + errors[0] : null;
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
