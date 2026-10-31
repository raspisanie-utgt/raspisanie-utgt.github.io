// Расписание преподавателя по расписаниям всех групп и заменам: его пары на день,
// где он сейчас и где следующая пара.
// Работает и в браузере (window.Teachers), и в node (require) — для тестов.
(function (root) {
  "use strict";

  var A = typeof module !== "undefined" && module.exports ? require("./agenda.js") : root.Agenda;
  var C = typeof module !== "undefined" && module.exports ? require("./calendar.js") : root.Calendar;

  function norm(s) {
    return String(s || "").replace(/Ё/g, "Е").replace(/ё/g, "е").replace(/\s+/g, " ").trim();
  }
  function split(s) { return String(s || "").split(" / "); }

  // Только буквы: «МДК.02.02. Тех. эксплуатация…» и «МДК 02.02 Тех эксплуатация…» совпадут
  function letters(s) { return norm(s).toLowerCase().replace(/[^а-яa-z0-9]/g, ""); }
  function distance(a, b) {
    if (Math.abs(a.length - b.length) > 3) return 99;
    var prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev[j] = j;
    for (i = 1; i <= a.length; i++) {
      cur = [i];
      for (j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
    return prev[b.length];
  }
  // Тот же предмет? С опечатками (в PDF есть «безопансость») и иностранный язык — по языку в скобках
  // («…в профессиональной деятельности (английский)» = «Иностранный язык (английский)»)
  // Код дисциплины в начале: «МДК.03.01», «ПМ.02», «ОП.05» — у похожих по названию МДК он разный
  function code(s) {
    var m = String(s).match(/^\s*(МДК|ПМ|ОП|ОГСЭ|ЕН|УП|ПП|ПДП|ОУД|УД|СГ|ОД|ПД)[.\s]*(\d+(?:[.\s]+\d+)*)/i);
    return m ? m[1].toUpperCase() + m[2].replace(/[.\s]+/g, ".") : null;
  }
  function sameSubject(a, b) {
    var ca = code(a), cb = code(b);
    if (ca && cb && ca !== cb) return false;  // разные коды — разные предметы, даже если названия почти одинаковые
    var x = letters(a), y = letters(b);
    if (x === y || (x.length > 12 && distance(x, y) <= 3)) return true;
    var la = /язык/i.test(a) && String(a).match(/\((\S+)\)\s*$/), lb = /язык/i.test(b) && String(b).match(/\((\S+)\)\s*$/);
    return !!(la && lb && la[1].toLowerCase() === lb[1].toLowerCase() && /иностран/i.test(a) && /иностран/i.test(b));
  }

  // В распоряжении о замене преподаватель не указан. Если предмет замены группа изучает
  // по расписанию у одного преподавателя — пара, скорее всего, его.
  function guessTeacher(schedule, subject) {
    var found = {};
    Object.keys(schedule.days).forEach(function (d) {
      schedule.days[d].forEach(function (e) {
        var subj = split(e.subject), teach = split(e.teacher);
        subj.forEach(function (s, i) {
          var t = teach[i] || teach[0];
          if (sameSubject(s, subject) && norm(t)) found[norm(t)] = t.trim();
        });
      });
    });
    var names = Object.keys(found);
    return names.length === 1 ? found[names[0]] : "";
  }

  // Пары преподавателя одной группы на дату (с заменами) и снятые с него пары
  function groupDay(who, s, date, bells, calendar, z) {
    var off = C.dayOff(date, calendar || {}, s.group);
    if (off && !(z && z.changes && z.changes.length)) return { items: [], removed: [] };
    // каникулы или практика, но в распоряжении есть строки для группы — только эти строки, без обычных пар
    var base = off ? Object.assign({}, s.schedule, { days: {} }) : s.schedule;
    var ag = A.build(date, base, bells, z), items = [];
    ag.items.forEach(function (it) {
      var names = split(it.teacher).map(norm), rooms = split(it.room), subj = split(it.subject);
      var i = names.indexOf(who), guessed = false;
      if (i < 0 && it.changed && !it.teacher && it.subject !== A.CANCEL && norm(guessTeacher(s.schedule, it.subject)) === who) {
        i = 0; guessed = true;
      }
      if (i < 0) return;
      items.push({ group: s.group, subject: subj[i] || subj[0], room: rooms[i] || rooms[0] || "",
        lessons: it.lessons, start: it.start, end: it.end, startText: it.startText, endText: it.endText,
        changed: !!it.changed, guessed: guessed, uncertain: !!it.uncertain, maybeCancel: !!it.maybeCancel });
    });
    // что было у него по расписанию, но после замен пропало
    var removed = [];
    if (z && z.changes && z.changes.length) {
      A.build(date, base, bells, null).items.forEach(function (it) {
        var names = split(it.teacher).map(norm), i = names.indexOf(who);
        if (i < 0) return;
        var still = items.some(function (x) { return x.start === it.start && norm(x.subject) === norm(split(it.subject)[i] || it.subject); });
        if (!still) removed.push({ group: s.group, subject: split(it.subject)[i] || it.subject, startText: it.startText, endText: it.endText, start: it.start });
      });
    }
    return { items: items, removed: removed };
  }

  // День преподавателя: пары по времени; одна и та же пара у нескольких групп (поток) — одной строкой
  // schedules: [{ group, schedule }]; zamena(group) -> замены группы на эту дату или null
  function day(teacher, date, schedules, bells, calendar, zamena) {
    var who = norm(teacher), all = [], removed = [];
    schedules.forEach(function (s) {
      var r = groupDay(who, s, date, bells, calendar, zamena ? zamena(s.group) : null);
      all = all.concat(r.items);
      removed = removed.concat(r.removed);
    });
    all.sort(function (a, b) { return a.start - b.start || a.group.localeCompare(b.group, "ru"); });
    var items = [];
    all.forEach(function (l) {
      var same = items.filter(function (x) { return x.start === l.start && norm(x.subject) === norm(l.subject); })[0];
      if (same) {
        same.groups.push(l.group);
        if (l.room && same.rooms.indexOf(l.room) < 0) same.rooms.push(l.room);
        same.changed = same.changed || l.changed;
        same.guessed = same.guessed || l.guessed;
        same.maybeCancel = same.maybeCancel || l.maybeCancel;
        return;
      }
      items.push({ groups: [l.group], rooms: l.room ? [l.room] : [], subject: l.subject, lessons: l.lessons,
        start: l.start, end: l.end, startText: l.startText, endText: l.endText,
        changed: l.changed, guessed: l.guessed, uncertain: l.uncertain, maybeCancel: l.maybeCancel });
    });
    removed.sort(function (a, b) { return a.start - b.start; });
    return { items: items, removed: removed };
  }

  // Где сейчас и где следующая пара — для подсказки в карточке урока
  function whereIs(teacher, date, minutes, schedules, bells, calendar, zamena) {
    var lessons = day(teacher, date, schedules, bells, calendar, zamena).items.map(function (l) {
      return { group: l.groups.join(", "), subject: l.subject, room: l.rooms.join(" / "), guessed: !!l.guessed,
        start: l.start, end: l.end, startText: l.startText, endText: l.endText };
    });
    // две пары в одно время (по расписанию и по замене, где преподаватель угадан) — верим расписанию
    function pick(ls) {
      return ls.filter(function (l) { return l.start === ls[0].start && !l.guessed; })[0] || ls[0] || null;
    }
    var now = pick(lessons.filter(function (l) { return l.start <= minutes && minutes < l.end; }));
    var next = pick(lessons.filter(function (l) { return l.start > minutes && (!now || l.start >= now.end); }));
    return { now: now, next: next, lessons: lessons };
  }

  // Все преподаватели из расписаний: короткое имя «Фамилия И.О.»
  function list(schedules) {
    var seen = {};
    schedules.forEach(function (s) {
      Object.keys(s.schedule.days).forEach(function (d) {
        s.schedule.days[d].forEach(function (e) {
          split(e.teacher).forEach(function (t) { if (norm(t)) seen[norm(t)] = true; });
        });
      });
    });
    return Object.keys(seen).sort(function (a, b) { return a.localeCompare(b, "ru"); });
  }

  var api = { whereIs: whereIs, day: day, list: list, guessTeacher: guessTeacher, sameSubject: sameSubject };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Teachers = api;
})(this);
