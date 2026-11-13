const assert = require('node:assert/strict');
const { test } = require('node:test');
const rules = require('../site/appearance-rules');
const renderer = require('../site/appearance-renderer');

const date = day => new Date(`2026-${day}T09:00:00Z`);
const select = (mode, day, extra, weather) => rules.select(rules.normalize({ mode, ...extra }), date(day), weather);
const storage = () => {
  const data = new Map();
  return { getItem: key => data.get(key), setItem: (key, value) => data.set(key, value) };
};

test('appearance settings default to off, persist and tolerate invalid stored data', () => {
  const store = storage();
  assert.equal(rules.normalize(rules.read(store, rules.settingsKey)).mode, 'off');
  const saved = rules.normalize({ mode: 'manual', manual: 'leaves', intensity: 150, holidays: false, accumulation: false, physics: false });
  rules.write(store, rules.settingsKey, saved);
  assert.deepEqual(rules.read(store, rules.settingsKey), { mode: 'manual', manual: 'leaves', intensity: 100,
    holidays: false, accumulation: false, physics: false });
  store.setItem(rules.settingsKey, '{broken');
  assert.equal(rules.read(store, rules.settingsKey), null);
  assert.doesNotThrow(() => rules.write(null, rules.settingsKey, saved));
});

test('mode, Moscow date boundaries, holidays and overlap priority', () => {
  assert.equal(rules.monthDay(new Date('2026-08-31T21:00:00Z')), '09-01');
  for (const [day, effect] of [['12-01', 'snow'], ['03-01', 'petals'], ['06-01', 'sun'], ['09-01', 'leaves']]) {
    assert.equal(select('season', day).effect, effect);
  }
  for (const effect of ['rain', 'leaves', 'petals', 'lights', 'none']) {
    assert.equal(select('manual', '01-07', { manual: effect }).effect, effect);
  }
  assert.equal(select('manual', '01-07', { manual: 'snow' }).effect, 'snow');
  assert.equal(select('manual', '01-07', { manual: 'snow' }).holiday[0], 'christmas');
  assert.equal(select('season', '12-24').holiday[0], 'new-year');
  assert.equal(select('season', '01-05').holiday[0], 'new-year');
  assert.equal(select('season', '01-06').holiday[0], 'christmas');
  for (const day of ['01-07', '02-14', '02-23', '03-08', '04-12', '05-01', '05-09', '06-12', '09-01', '10-05', '10-31', '11-04']) {
    assert.ok(rules.holiday(day), day);
  }
  assert.equal(rules.holiday('01-09'), null);
  assert.equal(select('off', '01-07').holiday, null);
  assert.equal(select('season', '01-07', { holidays: false }).holiday, null);
  assert.equal(select('season', '01-07', { intensity: 0 }).effect, 'none');
});

test('weather mapping and seasonal fallback for missing or unknown codes', () => {
  const map = (weather_code, is_day = 1) => select('weather', '01-10', {}, rules.parseWeather({ weather_code, is_day })).effect;
  assert.equal(map(85), 'snow');
  assert.equal(map(67), 'rain');
  assert.equal(map(99), 'rain');
  assert.equal(map(0), 'sun');
  assert.equal(map(1, 0), 'lights');
  assert.equal(map(48), 'cloud');
  assert.equal(map(500), 'snow');
});

test('weather calls coalesce, reuse cache, skip offline and back off after failure', async () => {
  let now = 10000;
  let calls = 0;
  let fail = false;
  const store = storage();
  const fetcher = async (url, options) => {
    calls++;
    assert.match(url, /latitude=63\.55446&longitude=53\.70041/);
    assert.equal(options.credentials, 'omit');
    return { ok: !fail, json: async () => ({ current: { weather_code: 73, wind_speed_10m: 10 } }) };
  };
  const weather = rules.createWeather(store, fetcher, () => now);
  assert.equal(await weather.load(false), null);
  const a = weather.load(true);
  assert.equal(a, weather.load(true));
  assert.equal((await a).code, 73);
  assert.equal((await rules.createWeather(store, fetcher, () => now).load(true)).code, 73);
  assert.equal(calls, 1);
  now += 31 * 60 * 1000;
  fail = true;
  assert.equal(weather.fresh(), null);
  assert.equal(await weather.load(true), null);
  assert.equal(await weather.load(true), null);
  assert.equal(calls, 2);
  now += 5 * 60 * 1000;
  fail = false;
  assert.equal((await weather.load(true)).code, 73);
  assert.equal(calls, 3);
});

test('snow growth, shedding and melting are bounded, including on small and wide devices', () => {
  const { budget, depth, shed, maxDepth } = renderer;
  assert.equal(depth(0, true, 100, 10000), maxDepth);
  assert.equal(depth(maxDepth, true, 40, 10), maxDepth * .4);
  assert.ok(shed(shed(maxDepth)) < shed(maxDepth));
  assert.equal(depth(0, false, 100, 10), 0);
  assert.equal(depth(maxDepth, false, 100, 40), 0);
  assert.equal(budget(360, 780, 3, 2, 8).count, 15);
  assert.equal(budget(3440, 1440, 2, 8, 4).count, 15);
  for (const [w, h] of [[360, 780], [412, 915], [2560, 1080], [3440, 1440]]) {
    const { scale } = budget(w, h, 3, 8, 8);
    assert.ok(Math.floor(w * scale) * Math.floor(h * scale) <= 1600000);
  }
});
