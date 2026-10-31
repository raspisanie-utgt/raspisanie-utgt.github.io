// Календарь учебного года: праздники, каникулы, сессия (из календарного учебного графика).
// Работает и в браузере (window.Calendar), и в node (require) — для тестов.
(function (root) {
  "use strict";

  var MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря"];

  function days(a, b) {
    return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
  }

  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  // 85 -> «1 час 25 минут», 60 -> «1 час», 40 -> «40 минут»
  function minutesText(n) {
    var h = Math.floor(n / 60), m = n % 60, out = [];
    if (h) out.push(h + " " + plural(h, "час", "часа", "часов"));
    if (m || !h) out.push(m + " " + plural(m, "минута", "минуты", "минут"));
    return out.join(" ");
  }

  function daysText(n) {
    return n + " " + plural(n, "день", "дня", "дней");
  }

  function dayMonth(iso) {
    var p = iso.split("-");
    return +p[2] + " " + MONTHS[+p[1] - 1];
  }

  function periods(cal, group) {
    return ((cal.groups || {})[group] || {}).periods || [];
  }

  // Государственные праздники, которые каждый год одни и те же (переносы выходных бывают разные — их знает только
  // учебный график). Нужны, когда учебного графика на этот год ещё нет: сайт всё равно не поставит пары на 4 ноября.
  var FIXED_HOLIDAYS = { "01-01": "Новогодние каникулы", "01-02": "Новогодние каникулы", "01-03": "Новогодние каникулы",
    "01-04": "Новогодние каникулы", "01-05": "Новогодние каникулы", "01-06": "Новогодние каникулы", "01-07": "Рождество Христово",
    "01-08": "Новогодние каникулы", "02-23": "День защитника Отечества", "03-08": "Международный женский день",
    "05-01": "Праздник Весны и Труда", "05-09": "День Победы", "06-12": "День России", "11-04": "День народного единства" };

  // Учебный год, который покрывает график: с 1 сентября до последнего дня периодов (обычно 31 августа)
  var RANGE = typeof WeakMap === "function" ? new WeakMap() : null;  // посчитанное — без пометок в самом графике
  function covered(date, cal) {
    var r = RANGE && RANGE.get(cal);
    if (!r) {
      var end = "";
      Object.keys(cal.groups || {}).forEach(function (g) { periods(cal, g).forEach(function (p) { if (p.to > end) end = p.to; }); });
      (cal.holidays || []).forEach(function (h) { if (h.date > end) end = h.date; });
      r = { start: end ? (+end.slice(0, 4) - 1) + "-09-01" : "9999", end: end || "0000" };
      if (RANGE) RANGE.set(cal, r);
    }
    return date >= r.start && date <= r.end;
  }

  function holiday(date, cal) {
    var h = (cal.holidays || []).filter(function (h) { return h.date === date; })[0] || null;
    if (h || covered(date, cal)) return h;
    var name = FIXED_HOLIDAYS[date.slice(5)];
    return name ? { date: date, name: name } : null;
  }

  // Нет занятий в этот день? -> { reason: "...", kind: "holiday"|"break" } или null
  function dayOff(date, cal, group) {
    var h = holiday(date, cal);
    if (h) return { kind: "holiday", reason: h.name };
    var p = periods(cal, group).filter(function (p) {
      return p.no_classes && p.from <= date && date <= p.to;
    })[0];
    return p ? { kind: "break", reason: p.name, until: p.to } : null;
  }

  // Строка под датой: что идёт сейчас и сколько осталось до ближайшего важного.
  // text — полностью (в пояснении по нажатию), short — на самой строке: «До каникул 61 день»,
  // за неделю и ближе — «До каникул осталось 7 дней»; выходной — «4 ноября выходной».
  // progress (0…1) — для полоски под строкой: сколько прошло от начала учёбы (1 сентября или конца
  // прошлых каникул/сессии) до каникул, или сколько прошло от идущего периода.
  function leftText(n) { return (n % 10 === 1 && n % 100 !== 11 ? "остался " : "осталось ") + daysText(n); }
  function untilText(what, n) { return what + " " + (n > 7 ? daysText(n) : leftText(n)); }
  function yearStart(today) {
    var y = +today.slice(0, 4);
    return (+today.slice(5, 7) >= 9 ? y : y - 1) + "-09-01";
  }
  function countdown(today, cal, group) {
    var out = [], ps = periods(cal, group);
    var now = ps.filter(function (p) { return p.from <= today && today <= p.to; })[0];
    if (now) {
      var left = days(today, now.to);
      var tail = left > 0 ? " — ещё " + daysText(left) : " — последний день";
      out.push({ kind: now.type, text: now.name + " до " + dayMonth(now.to) + tail, exams: now.exams || null,
        short: now.name + tail, progress: (days(now.from, today) + 1) / (days(now.from, now.to) + 1) });
    }
    var nextBreak = ps.filter(function (p) { return p.type === "kanikuly" && p.from > today; })[0];
    if (nextBreak && !(now && now.type === "kanikuly")) {
      var kd = days(today, nextBreak.from), start = yearStart(today);
      ps.forEach(function (p) { if (p.to < today && p.to >= start) start = addDays(p.to, 1); });
      out.push({ kind: "kanikuly", text: "До каникул " + daysText(kd) + " (с " + dayMonth(nextBreak.from) + ")",
        short: untilText("До каникул", kd), progress: Math.min(1, Math.max(0, days(start, today) / Math.max(1, days(start, nextBreak.from)))) });
    }
    var session = ps.filter(function (p) { return p.type === "sessiya" && p.from > today; })[0];
    if (session && days(today, session.from) <= 45) {
      var sd = days(today, session.from);
      out.push({ kind: "sessiya", text: "До сессии " + daysText(sd) + " (с " + dayMonth(session.from) + ")",
        exams: session.exams || null, short: untilText("До сессии", sd) });
    }
    var h = (cal.holidays || []).filter(function (h) { return h.date > today; })[0];
    if (h && days(today, h.date) <= 14 && !dayOff(h.date, { groups: cal.groups }, group)) {
      var d = days(today, h.date), when = d === 1 ? "Завтра" : dayMonth(h.date);
      out.push({ kind: "holiday", text: when + " выходной — " + h.name, short: when + " выходной" });
    }
    return out;
  }

  function toMin(hhmm) {
    var p = hhmm.split(":");
    return +p[0] * 60 + +p[1];
  }

  function weekday(iso) {
    var d = new Date(iso + "T00:00:00Z").getUTCDay();
    return d === 0 ? 7 : d;
  }

  function addDays(iso, n) {
    var d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }

  // Учебная часть сейчас: { open: bool, text: "Открыто до 16:30" | "Обед до 12:00" | "Закрыто, откроется …" }
  function officeStatus(date, minutes, office, cal) {
    function hours(d) {
      return holiday(d, cal || {}) ? null : office.hours[String(weekday(d))] || null;
    }
    var h = hours(date);
    if (h) {
      var open = toMin(h[0]), close = toMin(h[1]);
      var l0 = toMin(office.lunch[0]), l1 = toMin(office.lunch[1]);
      if (minutes >= l0 && minutes < l1) return { open: false, text: "Обед до " + office.lunch[1] };
      if (minutes >= open && minutes < close) return { open: true, text: "Открыто до " + h[1] };
      if (minutes < open) return { open: false, text: "Закрыто, откроется сегодня в " + h[0] };
    }
    for (var i = 1; i <= 14; i++) {
      var d = addDays(date, i), next = hours(d);
      if (next) {
        var when = i === 1 ? "завтра" : dayMonth(d);
        return { open: false, text: "Закрыто, откроется " + when + " в " + next[0] };
      }
    }
    return { open: false, text: "Закрыто" };
  }

  // Период учебного графика, в который попадает дата (сессия, практика, каникулы…), или null
  function current(date, cal, group) {
    return periods(cal, group).filter(function (p) { return p.from <= date && date <= p.to; })[0] || null;
  }

  var api = { current: current, dayOff: dayOff, countdown: countdown, officeStatus: officeStatus, plural: plural, daysText: daysText, minutesText: minutesText,
    dayMonth: dayMonth };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Calendar = api;
})(this);
