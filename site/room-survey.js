(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.UTGTRoomSurvey = factory();
})(typeof window === 'object' ? window : null, function () {
  'use strict';

  const days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
  const neverKey = 'utgt-room-survey-never';
  const skipKey = 'utgt-room-survey-skip';
  const missing = /^(?:\?|[12]-\?)?$/;
  const notClassroom = /разговоры о важном|учебная практика|производственная практика|преддипломная практика/i;

  function questions(schedule, group, date, period) {
    if (!group || !schedule || schedule.group !== group || !schedule.verified || !schedule.days || !date ||
        !period || !period.validFrom || !period.validTo || date < period.validFrom || date > period.validTo) return [];
    const result = [];
    const seen = new Set();
    for (let day = 1; day <= 6; day++) {
      const rows = schedule.days[day];
      if (!Array.isArray(rows)) continue;
      for (const row of rows) {
        if (!row || typeof row !== 'object') continue;
        const room = String(row.room || '').trim();
        const subject = typeof row.subject === 'string' ? row.subject.trim() : '';
        const lessons = row.lessons;
        if (!missing.test(room) || !subject || subject.includes(' / ') || notClassroom.test(subject) ||
            !Array.isArray(lessons) || !lessons.length || !lessons.every(n => Number.isInteger(n) && n >= 1 && n <= 12) ||
            (row.week != null && row.week !== 1 && row.week !== 2)) continue;
        // A competing row can describe a subgroup or a corrected room for the same slot.
        if (rows.some(other => other && other !== row && Array.isArray(other.lessons) &&
            (!row.week || !other.week || row.week === other.week) && other.lessons.some(n => lessons.includes(n)))) continue;
        const key = JSON.stringify([day, lessons, row.week || 0, subject, room]);
        if (seen.has(key)) continue;
        seen.add(key);
        result.push({ key, day, lessons, subject, week: row.week || 0, building: room.includes('-') ? room[0] : '' });
        if (result.length === 3) return result;
      }
    }
    return result;
  }

  function roomNumber(input, building) {
    const value = String(input || '').trim().toUpperCase().replace(/[–—−]/g, '-').replace(/\s*-\s*/g, '-');
    if (!value) return { valid: true, value: '' };
    const match = /^([12])-[1-9]\d{0,2}[А-ЯA-Z]?$/.exec(value);
    return match && (!building || match[1] === building) ? { valid: true, value } : { valid: false, value: '' };
  }

  function mount(win, doc) {
    const panel = doc.getElementById('roomSurvey');
    if (!panel) return { select() {}, update() {} };
    const form = doc.getElementById('roomSurveyForm');
    const fields = doc.getElementById('roomSurveyFields');
    const open = doc.getElementById('roomSurveyOpen');
    let group = null;
    let signature = '';
    const preference = (store, key, write) => {
      try {
        if (write) win[store].setItem(key, '1');
        return win[store].getItem(key) === '1';
      } catch (_) { return false; }
    };
    let dismissed = preference('sessionStorage', skipKey) || preference('localStorage', neverKey);

    function clear() {
      panel.hidden = true;
      form.hidden = true;
      open.hidden = false;
      open.setAttribute('aria-expanded', 'false');
      fields.textContent = '';
      signature = '';
    }

    function dismiss(permanent) {
      dismissed = true;
      preference('sessionStorage', skipKey, true);
      if (permanent) preference('localStorage', neverKey, true);
      clear();
    }

    function add(question, index) {
      const label = doc.createElement('label');
      const input = doc.createElement('input');
      const message = doc.createElement('small');
      const id = 'roomSurveyRoom' + index;
      input.id = label.htmlFor = id;
      input.type = 'text';
      input.maxLength = 12;
      input.autocomplete = 'off';
      input.spellcheck = false;
      input.placeholder = question.building ? question.building + '-7' : '1-25';
      label.textContent = days[question.day - 1] + ', уроки ' + question.lessons.join(', ') +
        (question.week ? ', неделя ' + question.week : '') + ' — ' + question.subject;
      message.id = id + 'Hint';
      message.hidden = true;
      input.setAttribute('aria-describedby', message.id);
      input.addEventListener('input', () => {
        const valid = roomNumber(input.value, question.building).valid;
        input.setAttribute('aria-invalid', String(!valid));
        message.hidden = valid;
        message.textContent = valid ? '' : 'Введите корпус и номер, например ' + input.placeholder + '.';
      });
      fields.append(label, input, message);
    }

    open.addEventListener('click', () => {
      open.setAttribute('aria-expanded', 'true');
      open.hidden = true;
      form.hidden = false;
      fields.querySelector('input').focus();
    });
    form.addEventListener('submit', event => event.preventDefault());
    doc.getElementById('roomSurveySkip').addEventListener('click', () => dismiss(false));
    doc.getElementById('roomSurveyNever').addEventListener('click', () => dismiss(true));
    win.addEventListener('storage', event => {
      if (event.key === neverKey && event.newValue === '1') dismiss(false);
    });

    return {
      select(next) { if (group !== next) { group = next; clear(); } },
      update(schedule, date, period) {
        if (dismissed) return;
        const list = questions(schedule, group, date, period);
        if (!list.length) { clear(); return; }
        const next = JSON.stringify([schedule.source, list.map(question => question.key)]);
        if (next === signature) return;
        clear();
        signature = next;
        list.forEach(add);
        panel.hidden = false;
      }
    };
  }

  return { mount, questions, roomNumber };
});
