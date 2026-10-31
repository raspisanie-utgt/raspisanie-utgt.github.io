// Сборка расписания на конкретный день: базовое расписание + звонки + замены.
// Работает и в браузере (window.Agenda), и в node (require) — для тестов.
(function (root) {
  "use strict";

  var CANCEL = "Отменить";
  var WEEKDAYS = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];
  var MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря"];

  function toMin(hhmm) {
    var p = hhmm.split(":");
    return +p[0] * 60 + +p[1];
  }

  function fromMin(m) {
    var h = Math.floor(m / 60), mm = m % 60;
    return (h < 10 ? "0" : "") + h + ":" + (mm < 10 ? "0" : "") + mm;
  }

  // "2026-10-26" -> 1..7 (1 = понедельник)
  function isoWeekday(iso) {
    var p = iso.split("-");
    var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay();
    return d === 0 ? 7 : d;
  }

  function addDays(iso, n) {
    var p = iso.split("-");
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + n)).toISOString().slice(0, 10);
  }

  function humanDate(iso) {
    var p = iso.split("-");
    var wd = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay();
    return WEEKDAYS[wd] + ", " + +p[2] + " " + MONTHS[+p[1] - 1];
  }

  // Время урока: пара делится на два урока по lesson_minutes без перемены.
  function lessonTime(bells, weekday, n) {
    var day = weekday === 1 ? bells.monday : bells.other_days;
    if (n === 0) {
      var r = bells.monday.razgovory;
      return { start: toMin(r[0]), end: toMin(r[1]) };
    }
    var pair = day.pairs[String(Math.ceil(n / 2))];
    if (!pair) return null;
    var s = toMin(pair[0]), e = toMin(pair[1]), len = bells.lesson_minutes;
    return n % 2 === 1 ? { start: s, end: s + len } : { start: e - len, end: e };
  }

  // Номер учебной недели (1 или 2). Если в распоряжении о замене написано
  // «2-я неделя» — верим ему, иначе считаем от опорной даты из расписания.
  function weekNumber(date, schedule, zamena) {
    var m = zamena && zamena.title && zamena.title.match(/([12])\s*-?\s*я\s+недел/i);
    // заголовок не совпал с расчётом (scraper.py: week_doubt) — скорее всего, цифра прочитана неверно: верим расчёту
    if (m && !zamena.week_doubt) return +m[1];
    var a = schedule.week_anchor;
    if (!a) return 1;
    var days = Math.round((Date.parse(date) - Date.parse(a.date)) / 86400000);
    var weeks = Math.floor(days / 7);
    return ((((weeks % 2) + 2) % 2) === 0) ? a.week : 3 - a.week;
  }

  // Номер части составной пары («английский / немецкий»), которую заменяет строка распоряжения, или -1.
  // Только для пар из нескольких частей: язык замены совпал с языком одной из частей или совпал сам предмет.
  function part(oldSubject, subject) {
    var parts = String(oldSubject).split(" / ");
    if (parts.length < 2) return -1;
    var l = langOf(subject);
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] === subject || (l && langOf(parts[i]) === l)) return i;
    }
    return -1;
  }

  // Возвращает { items: [...], cancelled: [...], changed: bool, week: 1|2 }
  function build(date, schedule, bells, zamena) {
    var wd = isoWeekday(date);
    var week = weekNumber(date, schedule, zamena);
    var byLesson = {};
    (schedule.days[String(wd)] || []).forEach(function (b, i) {
      if (b.week && b.week !== week) return;
      b.lessons.forEach(function (n) {
        byLesson[n] = { subject: b.subject, teacher: b.teacher, room: b.room, block: "b" + i, changed: false };
      });
    });

    var cancelled = [], extra = [];
    var changes = (zamena && zamena.changes) || [];
    changes.forEach(function (c, i) {
      // строка со временем вместо урока («8-30»): в понедельник до первой пары — это «Разговоры о важном»
      // (урок 0) — меняем их кабинет или отменяем их, а не добавляем вторую карточку
      if (!c.lessons.length && c.time && wd === 1 && toMin(c.time) < toMin(bells.monday.pairs["1"][0])) {
        c = Object.assign({}, c, { lessons: [0] });
      }
      if (!c.lessons.length) {
        if (c.time && c.subject !== CANCEL) {
          var t = toMin(c.time);
          extra.push({ lessons: [], start: t, end: t + 45, subject: c.subject, teacher: "", room: c.room,
            changed: true, uncertain: c.uncertain });
        }
        return;
      }
      c.lessons.forEach(function (n) {
        var old = byLesson[n];
        if (c.subject === CANCEL && c.uncertain) {
          // отмена распознана неуверенно — пару не убираем (вдруг она есть), а помечаем «возможно, отменена»
          if (old) byLesson[n] = Object.assign({}, old, { maybeCancel: true, uncertain: true });
        } else if (c.subject === CANCEL) {
          if (old) cancelled.push({ n: n, subject: old.subject, teacher: old.teacher, room: old.room });
          delete byLesson[n];
        } else if (old && part(old.subject, c.subject) >= 0) {
          // пара у двух языковых подгрупп («английский / немецкий»), замена — у одной: меняем только её часть,
          // вторая подгруппа остаётся со своей парой, преподавателем и кабинетом
          var k = part(old.subject, c.subject), sp = old.subject.split(" / "), tp = String(old.teacher || "").split(" / "),
            rp = String(old.room || "").split(" / ");
          var same1 = sp[k] === c.subject;
          sp[k] = c.subject;
          if (!same1) tp[k] = "";
          if (c.room) rp[k] = c.room;
          byLesson[n] = Object.assign({}, old, { subject: sp.join(" / "), teacher: tp.join(" / "), room: rp.join(" / "),
            block: "z" + i, changed: !(same1 && (!c.room || c.room === String(old.room).split(" / ")[k])), uncertain: c.uncertain });
        } else {
          var same = old && old.subject === c.subject;
          byLesson[n] = {
            subject: c.subject,
            teacher: same ? old.teacher : "",
            room: c.room || (same ? old.room : ""),
            block: "z" + i,
            changed: !(same && (!c.room || c.room === old.room)),
            was: old && !same ? old.subject : null,
            uncertain: c.uncertain
          };
        }
      });
    });

    // Склеиваем соседние уроки одного блока в одну строку
    var nums = Object.keys(byLesson).map(Number).sort(function (a, b) { return a - b; });
    var items = [];
    nums.forEach(function (n) {
      var l = byLesson[n], t = lessonTime(bells, wd, n);
      if (!t) return;
      var last = items[items.length - 1];
      if (last && last.block === l.block && !!last.maybeCancel === !!l.maybeCancel && last.lessons[last.lessons.length - 1] === n - 1) {
        last.lessons.push(n);
        last.end = t.end;
        return;
      }
      items.push({ lessons: [n], start: t.start, end: t.end, subject: l.subject, teacher: l.teacher,
        room: l.room, block: l.block, changed: l.changed, was: l.was || null, uncertain: !!l.uncertain,
        maybeCancel: !!l.maybeCancel });
    });
    items = items.concat(extra).sort(function (a, b) { return a.start - b.start; });
    items.forEach(function (it) {
      it.startText = fromMin(it.start);
      it.endText = fromMin(it.end);
      delete it.block;
    });

    // Отменённые уроки, которые потом заменили другим предметом, отменой не считаем
    cancelled = mergeCancelled(cancelled.filter(function (c) { return !byLesson[c.n]; }), bells, wd);
    return { date: date, weekday: wd, week: week, items: items, cancelled: cancelled,
      changed: cancelled.length > 0 || items.some(function (i) { return i.changed || i.maybeCancel; }) };
  }

  function mergeCancelled(list, bells, wd) {
    var out = [];
    list.sort(function (a, b) { return a.n - b.n; }).forEach(function (c) {
      var t = lessonTime(bells, wd, c.n), last = out[out.length - 1];
      if (last && last.subject === c.subject && last.lessons[last.lessons.length - 1] === c.n - 1) {
        last.lessons.push(c.n);
        last.endText = fromMin(t.end);
      } else {
        out.push({ lessons: [c.n], subject: c.subject, teacher: c.teacher, room: c.room,
          startText: fromMin(t.start), endText: fromMin(t.end) });
      }
    });
    return out;
  }

  // Статус каждого урока относительно текущего времени (минуты от полуночи)
  function markNow(agenda, nowMin) {
    var nextFound = false;
    agenda.items.forEach(function (it) {
      if (nowMin >= it.end) it.state = "past";
      else if (nowMin >= it.start) it.state = "now";
      else if (!nextFound) { it.state = "next"; nextFound = true; }
      else it.state = "later";
    });
    return agenda;
  }

  // Текущие дата и время в Ухте (Europe/Moscow)
  // В Москве всегда UTC+3 (переходов на летнее время нет с 2014 года) — считаем сдвигом, без Intl:
  // его первый вызов на слабом телефоне заметно подтормаживает загрузку
  function moscowNow(d) {
    var iso = new Date((d || new Date()).getTime() + 3 * 3600e3).toISOString();
    var h = +iso.slice(11, 13), m = +iso.slice(14, 16);
    return { date: iso.slice(0, 10), minutes: h * 60 + m, time: iso.slice(11, 16) };
  }

  // Иностранный язык подгруппы: «Иностранный язык (немецкий)» -> «немецкий», иначе null
  function langOf(subject) {
    var m = String(subject).match(/иностранн[^(]*\(([а-яё]+)\)/i);
    return m ? m[1].toLowerCase() : null;
  }

  // Оставить только пары своей языковой подгруппы. lang не выбран — всё как есть,
  // но у пар одного языка ставится item.langOnly (например, общий немецкий у всего 1 курса).
  function forLanguage(agenda, lang) {
    var items = [];
    agenda.items.forEach(function (it) {
      var subj = String(it.subject).split(" / "), teach = String(it.teacher || "").split(" / "),
        rooms = String(it.room || "").split(" / ");
      var keep = subj.map(function (s, i) { return i; }).filter(function (i) {
        var l = langOf(subj[i]);
        return !lang || !l || l === lang;
      });
      if (!keep.length) return;
      var pick = function (arr) {
        return arr.length === subj.length ? keep.map(function (i) { return arr[i]; }).join(" / ") : arr.join(" / ");
      };
      var copy = Object.assign({}, it, { subject: pick(subj), teacher: pick(teach), room: pick(rooms) });
      var langs = keep.map(function (i) { return langOf(subj[i]); });
      copy.langOnly = !lang && subj.length === 1 && langs[0] ? langs[0] : null;
      copy.lang = langs.filter(Boolean)[0] || null;
      items.push(copy);
    });
    return Object.assign({}, agenda, { items: items });
  }

  // ---------- общее для сайта и бота домашки (бот берёт этот файл прямо с сайта — правки доходят до него сами) ----------

  // Строки распоряжения для одной группы (файл распоряжения один на весь техникум)
  function zamenaForGroup(z, group) {
    if (!z || z.load_failed) return z || null;
    var all = z.all_changes, mine = all ? (all[group] || []) : [];
    return Object.assign({}, z, {
      changes: mine,
      // не по всем строкам распознана группа (или название группы прочитано криво — строка может быть чьей угодно),
      // номер недели под сомнением, или в файле нет разбивки по группам
      ocr_uncertain: !all || !!all["?"] || !!z.ocr_group_doubt || !!z.week_doubt || mine.some(function (c) { return c.uncertain; })
    });
  }

  // День группы целиком: в каникулы и на практике (off — Calendar.dayOff) — только строки замен,
  // после конца семестра (validTo — data/groups/index.json: valid_to) — ничего (ag.expired)
  function groupDay(date, schedule, bells, z, off, validTo) {
    var ag = build(date, off ? Object.assign({}, schedule, { days: {} }) : schedule, bells, z);
    ag.off = off || null;
    if (off && !(z && z.changes && z.changes.length)) { ag.items = []; ag.cancelled = []; }
    if (validTo && date > validTo) { ag.items = []; ag.cancelled = []; ag.expired = true; }
    return ag;
  }

  // Коротко, одной строкой (ответ бота «какие пары»): «Химия, Физика (возможно, отменена).» и пометки
  function shortText(ag, z) {
    if (ag.expired) return "расписания нового семестра на сайте пока нет — смотрите на сайте техникума.";
    var parts = [];
    ag.items.forEach(function (it) {
      if (/Разговоры о важном/i.test(it.subject)) return;
      var s = it.subject + (it.maybeCancel ? " (возможно, отменена)" : "");
      if (parts.indexOf(s) < 0) parts.push(s);
    });
    if (!parts.length) return "пар нет" + (ag.off ? " — " + ag.off.reason : ag.weekday === 7 ? " — воскресенье" : "") + ".";
    return parts.join(", ") + "." + (z && (z.load_failed || z.ocr_uncertain || !z.ocr_ok)
      ? " Замены распознаны неуверенно — сверьтесь с картинкой на сайте." : "");
  }

  // Данные давно не обновлялись (ежечасная проверка встала): «31.10 в 15:49» или "".
  // Днём проверка раз в час — тревога через 3 часа; ночью проверок нет (21:47–6:47) — через 12 часов.
  function staleSince(status, now) {
    var st = status || {}, at = st.checked_at && Date.parse(st.checked_at);
    if (!at) return "";
    var hours = ((now || new Date()) - at) / 36e5, h = moscowNow(now).minutes / 60;
    if (hours <= (h >= 9 && h < 22 ? 3 : 12)) return "";
    return st.checked_at.slice(8, 10) + "." + st.checked_at.slice(5, 7) + " в " + st.checked_at.slice(11, 16);
  }

  // BOT_API — версия того, чем пользуется бот домашки (dz-bot/bot.gs): zamenaForGroup, groupDay, shortText, staleSince.
  // Поменяли их вид — поднять версию и поправить бота (тест «договор с ботом» в tests/agenda.test.js напомнит).
  var api = { BOT_API: 1, langOf: langOf, forLanguage: forLanguage, build: build, zamenaForGroup: zamenaForGroup, groupDay: groupDay,
    shortText: shortText, staleSince: staleSince, weekNumber: weekNumber, markNow: markNow, moscowNow: moscowNow, isoWeekday: isoWeekday,
    addDays: addDays, humanDate: humanDate, lessonTime: lessonTime, CANCEL: CANCEL };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Agenda = api;
})(this);
