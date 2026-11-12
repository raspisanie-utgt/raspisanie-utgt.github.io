(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.UTGTAppearance = factory();
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const settingsKey = 'utgt-appearance-v1';
  const weatherKey = 'utgt-ukhta-weather-v1';
  const weatherURL = 'https://api.open-meteo.com/v1/forecast?latitude=63.55446&longitude=53.70041&current=weather_code,is_day,wind_speed_10m,wind_direction_10m&timezone=Europe%2FMoscow';
  const weatherAge = 30 * 60 * 1000;
  const retryDelay = 5 * 60 * 1000;
  const defaults = Object.freeze({ mode: 'off', manual: 'snow', intensity: 45, holidays: true, accumulation: true, physics: true });
  const modes = ['weather', 'season', 'manual', 'off'];
  const manualEffects = ['snow', 'rain', 'leaves', 'petals', 'lights', 'none'];
  const localDate = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Moscow', month: '2-digit', day: '2-digit' });

  // ID, label, inclusive MM-DD window, priority, and up to two decorative symbols.
  const holidays = [
    ['new-year', 'Новый год', '12-24', '01-06', 30, '✦', '🎄'],
    ['christmas', 'Рождество', '01-06', '01-08', 40, '✧', '✦'],
    ['valentine', 'День святого Валентина', '02-14', '02-14', 20, '♡', '♥'],
    ['defender', 'День защитника Отечества', '02-23', '02-23', 30, '✦', '✧'],
    ['women', 'Международный женский день', '03-08', '03-08', 30, '🌷', '❀'],
    ['space', 'День космонавтики', '04-12', '04-12', 30, '✦', '🪐'],
    ['labour', 'Праздник Весны и Труда', '05-01', '05-01', 30, '🌿', '❀'],
    ['victory', 'День Победы', '05-09', '05-09', 50, '🕯', '❀'],
    ['russia', 'День России', '06-12', '06-12', 30, '✧', '🇷🇺'],
    ['knowledge', 'День знаний', '09-01', '09-01', 30, '✦', '🍁'],
    ['teachers', 'День учителя', '10-05', '10-05', 30, '✧', '🌼'],
    ['halloween', 'Хеллоуин', '10-31', '10-31', 20, '🎃', '🦇'],
    ['unity', 'День народного единства', '11-04', '11-04', 30, '✦', '✧']
  ];

  const snow = new Set([71, 73, 75, 77, 85, 86]);
  const rain = new Set([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99]);
  const validWeather = new Set([0, 1, 2, 3, 45, 48, ...snow, ...rain]);
  const clamp = (n, min, max) => Math.min(max, Math.max(min, n));

  function normalize(value = {}) {
    value = value && typeof value === 'object' ? value : {};
    return {
      mode: modes.includes(value.mode) ? value.mode : defaults.mode,
      manual: manualEffects.includes(value.manual) ? value.manual : defaults.manual,
      intensity: Number.isFinite(value.intensity) ? clamp(Math.round(value.intensity), 0, 100) : defaults.intensity,
      holidays: typeof value.holidays === 'boolean' ? value.holidays : defaults.holidays,
      accumulation: typeof value.accumulation === 'boolean' ? value.accumulation : defaults.accumulation,
      physics: typeof value.physics === 'boolean' ? value.physics : defaults.physics
    };
  }

  function read(storage, key) {
    try { return JSON.parse(storage.getItem(key)); } catch (_) { return null; }
  }

  function write(storage, key, value) {
    try { storage.setItem(key, JSON.stringify(value)); } catch (_) { /* session settings still work */ }
  }

  function monthDay(date) {
    const parts = localDate.formatToParts(date);
    return parts.find(p => p.type === 'month').value + '-' + parts.find(p => p.type === 'day').value;
  }

  function season(day) {
    if (day < '03-01' || day >= '12-01') return 'snow';
    if (day < '06-01') return 'petals';
    if (day < '09-01') return 'sun';
    return 'leaves';
  }

  function holiday(day) {
    let winner = null;
    for (const event of holidays) {
      const [, , start, end, priority] = event;
      const active = start <= end ? day >= start && day <= end : day >= start || day <= end;
      if (active && (!winner || priority > winner[4])) winner = event;
    }
    return winner;
  }

  function parseWeather(current) {
    if (!current || !validWeather.has(current.weather_code)) return null;
    const speed = Number.isFinite(current.wind_speed_10m) ? clamp(current.wind_speed_10m, 0, 60) : 0;
    const direction = Number.isFinite(current.wind_direction_10m) ? current.wind_direction_10m : 0;
    return { code: current.weather_code, day: current.is_day !== 0, wind: -Math.sin(direction * Math.PI / 180) * speed / 5 };
  }

  function select(prefs, date, weather) {
    if (prefs.mode === 'off' || !prefs.intensity) return { effect: 'none', holiday: null, wind: 0 };
    const day = monthDay(date);
    let effect = prefs.mode === 'manual' ? prefs.manual : season(day);
    if (prefs.mode === 'weather' && weather) {
      if (snow.has(weather.code)) effect = 'snow';
      else if (rain.has(weather.code)) effect = 'rain';
      else if (weather.code <= 1) effect = weather.day ? 'sun' : 'lights';
      else effect = 'cloud';
    }
    // Snow stays disabled in production until the visual redesign is approved.
    return { effect: effect === 'snow' ? 'none' : effect, holiday: prefs.holidays ? holiday(day) : null,
      wind: prefs.mode === 'weather' && weather ? weather.wind : 0 };
  }

  function createWeather(storage, fetcher, now = Date.now) {
    let cached = read(storage, weatherKey);
    let nextAttempt = 0;
    let pending = null;
    function fresh() {
      return cached && Number.isFinite(cached.at) && now() >= cached.at && now() - cached.at < weatherAge &&
        cached.value && validWeather.has(cached.value.code) && Number.isFinite(cached.value.wind) ? cached.value : null;
    }
    function load(online) {
      if (!online) return Promise.resolve(null);
      if (pending) return pending;
      const shared = read(storage, weatherKey);
      if (shared && (!cached || shared.at > cached.at)) cached = shared;
      const hit = fresh();
      if (hit || now() < nextAttempt) return Promise.resolve(hit);
      nextAttempt = now() + retryDelay;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4500);
      pending = Promise.resolve().then(() => fetcher(weatherURL, { signal: controller.signal, credentials: 'omit', referrerPolicy: 'no-referrer' }))
        .then(response => response.ok ? response.json() : null)
        .then(data => {
          const value = parseWeather(data && data.current);
          if (value) {
            cached = { at: now(), value };
            write(storage, weatherKey, cached);
          }
          return value;
        }).catch(() => null).finally(() => { clearTimeout(timeout); pending = null; });
      return pending;
    }
    return { fresh, load };
  }

  return { settingsKey, read, write, normalize, monthDay, season, holiday, parseWeather, select, createWeather, clamp };
});
