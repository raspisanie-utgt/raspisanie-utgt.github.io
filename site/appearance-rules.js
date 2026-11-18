(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.UTGTAppearance = factory();
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const settingsKey = 'utgt-appearance-v1';
  const defaults = Object.freeze({ mode: 'off', manual: 'snow', intensity: 45, holidays: true, accumulation: true, physics: true });
  const modes = ['season', 'manual', 'off'];
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

  function select(prefs, date) {
    if (!modes.includes(prefs.mode) || prefs.mode === 'off' || !prefs.intensity) return { effect: 'none', holiday: null, wind: 0 };
    const day = monthDay(date);
    let effect = prefs.mode === 'manual' ? prefs.manual : season(day);
    // Temporarily disable snow in production until mobile rendering is repaired.
    if (effect === 'snow') effect = 'none';
    return { effect, holiday: prefs.holidays ? holiday(day) : null,
      wind: 0 };
  }

  return { settingsKey, read, write, normalize, monthDay, season, holiday, select, clamp };
});
