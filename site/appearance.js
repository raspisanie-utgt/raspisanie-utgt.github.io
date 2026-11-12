(function (win, doc, rules, rendering) {
  'use strict';

  const button = doc.getElementById('appearanceBtn');
  const dialog = doc.getElementById('appearanceDialog');
  if (!button || !dialog || !rules || !rendering) return;
  const form = doc.getElementById('appearanceForm');
  const fields = form.elements;
  const manual = doc.getElementById('appearanceManual');
  const intensity = doc.getElementById('appearanceIntensity');
  const holidayLabel = doc.getElementById('appearanceHoliday');
  const weatherNote = doc.getElementById('appearanceWeather');
  const motion = win.matchMedia('(prefers-reduced-motion: reduce)');
  let storage;
  try { storage = win.localStorage; } catch (_) { /* session only */ }
  let prefs = rules.normalize(rules.read(storage, rules.settingsKey));
  const renderer = rendering.create(win, doc);
  const weather = rules.createWeather(storage, win.fetch.bind(win));
  let timer = 0;

  function apply() {
    const current = prefs.mode === 'weather' && win.navigator.onLine ? weather.fresh() : null;
    const visual = rules.select(prefs, new Date(), current);
    renderer.configure(prefs, visual, motion.matches);
    holidayLabel.hidden = !visual.holiday;
    holidayLabel.textContent = visual.holiday ? visual.holiday[1] : '';
  }

  function update() {
    clearTimeout(timer);
    apply();
    if (doc.hidden || prefs.mode === 'off' || !prefs.intensity) return;
    if (prefs.mode === 'weather' && win.navigator.onLine && !weather.fresh()) {
      weather.load(true).then(() => { if (prefs.mode === 'weather' && !doc.hidden) apply(); });
    }
    // Re-evaluate the college's date and cache expiry in a long-lived tab.
    timer = setTimeout(update, 60000);
  }

  function syncForm() {
    fields.mode.value = prefs.mode;
    fields.manual.value = prefs.manual;
    fields.intensity.value = prefs.intensity;
    fields.holidays.checked = prefs.holidays;
    fields.accumulation.checked = prefs.accumulation;
    fields.physics.checked = prefs.physics;
    manual.hidden = prefs.mode !== 'manual';
    intensity.value = prefs.intensity + '%';
    weatherNote.hidden = prefs.mode !== 'weather';
    fields.physics.disabled = !prefs.accumulation;
  }

  form.addEventListener('input', () => {
    prefs = rules.normalize({ mode: fields.mode.value, manual: fields.manual.value, intensity: Number(fields.intensity.value),
      holidays: fields.holidays.checked, accumulation: fields.accumulation.checked, physics: fields.physics.checked });
    rules.write(storage, rules.settingsKey, prefs);
    syncForm();
    update();
  });

  function close() {
    if (dialog.close) dialog.close();
    else { dialog.removeAttribute('open'); button.focus(); }
  }
  button.addEventListener('click', () => {
    if (dialog.showModal) dialog.showModal();
    else { dialog.setAttribute('open', ''); fields.mode.focus(); }
  });
  form.addEventListener('submit', event => { event.preventDefault(); close(); });
  dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
  dialog.addEventListener('keydown', event => { if (event.key === 'Escape' && !dialog.close) close(); });
  win.addEventListener('online', update);
  win.addEventListener('offline', update);
  win.addEventListener('storage', event => {
    if (event.key !== rules.settingsKey && event.key !== null) return;
    prefs = rules.normalize(rules.read(storage, rules.settingsKey));
    syncForm();
    update();
  });
  doc.addEventListener('visibilitychange', update);
  if (motion.addEventListener) motion.addEventListener('change', update);
  else motion.addListener(update);
  syncForm();
  button.hidden = false;
  update();
})(window, document, window.UTGTAppearance, window.UTGTAppearanceRenderer);
