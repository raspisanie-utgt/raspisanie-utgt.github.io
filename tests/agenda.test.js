// node --test tests/agenda.test.js
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");
const A = require("../site/agenda.js");

const root = path.join(__dirname, "..");
const schedule = JSON.parse(fs.readFileSync(path.join(root, "data/groups/11a.json"), "utf8"));
const bells = JSON.parse(fs.readFileSync(path.join(root, "data/bells.json"), "utf8"));
const brief = (ag) => ag.items.map((i) => `${i.startText}-${i.endText} ${i.subject} ${i.room}${i.changed ? " *" : ""}`);

test("понедельник 26.10 без замен", () => {
  assert.deepStrictEqual(brief(A.build("2026-10-26", schedule, bells, null)), [
    "08:30-09:15 Разговоры о важном ",
    "09:20-10:50 Информатика 1-25",
    "11:00-12:30 Математика 1-8",
    "13:10-14:40 География 2-7",
  ]);
});

test("понедельник: строка «8-30» в заменах — это «Разговоры о важном», а не вторая карточка", () => {
  const z = (subject, room) => ({ changes: [{ lessons: [], time: "08:30", subject, room, uncertain: false }] });
  const ag = A.build("2026-11-02", schedule, bells, z("Разговоры о важном", "1-25"));
  assert.deepStrictEqual(brief(ag).slice(0, 2), ["08:30-09:15 Разговоры о важном 1-25 *", "09:20-10:50 Информатика 1-25"]);
  const off = A.build("2026-11-02", schedule, bells, z("Отменить", ""));
  assert.strictEqual(off.items[0].subject, "Информатика");
  assert.deepStrictEqual(off.cancelled.map((c) => c.subject), ["Разговоры о важном"]);
});

test("пятница, 3-я пара: 1-я неделя История, 2-я неделя Литература (на всю пару)", () => {
  const w1 = A.build("2026-10-23", schedule, bells, null);
  const w2 = A.build("2026-10-30", schedule, bells, null);
  assert.deepStrictEqual([w1.week, w2.week], [1, 2]);
  assert.deepStrictEqual(brief(w1).slice(2), ["12:50-14:20 История 2-10"]);
  assert.deepStrictEqual(brief(w2).slice(2), ["12:50-14:20 Литература 2-18"]);
});

test("суббота, 3-я пара по неделям", () => {
  assert.deepStrictEqual(brief(A.build("2026-10-31", schedule, bells, null)).slice(2), ["12:50-14:20 Физика 2-5"]);
  assert.deepStrictEqual(brief(A.build("2026-11-07", schedule, bells, null)).slice(2), ["12:50-14:20 Математика 1-8"]);
});

test("номер недели: от опорной даты, через Новый год, и из распоряжения", () => {
  const wk = (d, z) => A.weekNumber(d, schedule, z || null);
  assert.deepStrictEqual(["2026-10-19", "2026-10-25", "2026-10-26", "2026-11-02", "2026-12-28", "2027-01-04"].map((d) => wk(d)),
    [1, 1, 2, 1, 1, 2]);
  assert.strictEqual(wk("2026-10-27", { title: "Вторник, 2-я неделя" }), 2);
  assert.strictEqual(wk("2026-10-27", { title: "Вторник, 1-я неделя" }), 1); // распоряжение важнее расчёта
  assert.strictEqual(wk("2026-10-27", { title: "" }), 2);
});

test("суббота 24.10 с реальными заменами", () => {
  const z = { changes: [
    { lessons: [1, 2], subject: "Математика", room: "1-8" },
    { lessons: [5, 6], subject: "Химия", room: "2-7" },
    { lessons: [7, 8], subject: "Биология", room: "2-7" },
  ] };
  const ag = A.build("2026-10-24", schedule, bells, z);
  assert.deepStrictEqual(brief(ag), [
    "09:00-10:30 Математика 1-8 *",
    "10:40-12:10 Обществознание 2-10",
    "12:50-14:20 Химия 2-7 *",
    "14:30-16:00 Биология 2-7 *",
  ]);
  assert.strictEqual(ag.items[0].was, "Химия");
  assert.ok(ag.changed);
});

test("отмена урока попадает в список отменённых", () => {
  const ag = A.build("2026-10-27", schedule, bells, { changes: [{ lessons: [3, 4], subject: "Отменить", room: "" }] });
  assert.deepStrictEqual(brief(ag), ["09:00-10:30 Литература 2-18", "12:50-14:20 История 2-10"]);
  assert.deepStrictEqual(ag.cancelled.map((c) => `${c.subject} ${c.startText}-${c.endText}`), ["Физика 10:40-12:10"]);
});

test("замена с тем же предметом и кабинетом не считается изменением", () => {
  const ag = A.build("2026-10-26", schedule, bells, { changes: [{ lessons: [0], subject: "Разговоры о важном", room: "1-25" }] });
  assert.strictEqual(ag.items[0].room, "1-25");
  assert.strictEqual(ag.items[0].changed, true); // кабинет появился — это новая информация
  const same = A.build("2026-10-26", schedule, bells, { changes: [{ lessons: [1, 2], subject: "Информатика", room: "1-25" }] });
  assert.strictEqual(same.changed, false);
});

test("статусы идёт/далее", () => {
  const ag = A.markNow(A.build("2026-10-27", schedule, bells, null), 11 * 60);
  assert.deepStrictEqual(ag.items.map((i) => i.state), ["past", "now", "next"]);
});

test("воскресенье пустое, московская дата считается верно", () => {
  assert.strictEqual(A.build("2026-11-01", schedule, bells, null).items.length, 0);
  const now = A.moscowNow(new Date("2026-10-26T21:30:00Z"));
  assert.deepStrictEqual([now.date, now.time], ["2026-10-27", "00:30"]);
});

test("языковая подгруппа: чужой язык скрывается, подгруппы «А / Б» делятся", () => {
  const ag = { items: [
    { subject: "Иностранный язык (немецкий)", teacher: "Хаменева И.И.", room: "1-14" },
    { subject: "Иностранный язык (английский) / Иностранный язык (немецкий)", teacher: "Баякчан Л.А. / Хаменева И.И.", room: "2-15 / 1-14" },
    { subject: "Математика", teacher: "Трудова С.В.", room: "1-8" },
  ] };
  const en = A.forLanguage(ag, "английский").items;
  assert.deepStrictEqual(en.map((i) => [i.subject, i.teacher, i.room]), [
    ["Иностранный язык (английский)", "Баякчан Л.А.", "2-15"], ["Математика", "Трудова С.В.", "1-8"]]);
  const all = A.forLanguage(ag, null).items;
  assert.strictEqual(all.length, 3);
  assert.strictEqual(all[0].langOnly, "немецкий");
  assert.strictEqual(all[1].langOnly, null);
  assert.strictEqual(A.langOf("Иностранный язык в профессиональной деятельности (английский)"), "английский");
  assert.strictEqual(A.langOf("Русский язык"), null);
});

test("неуверенная отмена: пара не исчезает, а помечена «возможно, отменена»", () => {
  const z = (uncertain) => ({ changes: [{ lessons: [1, 2], time: null, subject: "Отменить", room: "", uncertain }] });
  const sure = A.build("2026-10-26", schedule, bells, z(false));
  assert.ok(!sure.items.some((i) => i.subject === "Информатика"));
  assert.deepStrictEqual(sure.cancelled.map((c) => c.subject), ["Информатика"]);
  const maybe = A.build("2026-10-26", schedule, bells, z(true));
  const it = maybe.items.find((i) => i.subject === "Информатика");
  assert.ok(it && it.maybeCancel && it.uncertain);
  assert.deepStrictEqual(maybe.cancelled, []);
});

test("заголовок распоряжения с сомнительной неделей (week_doubt) — неделя по расчёту", () => {
  assert.strictEqual(A.weekNumber("2026-10-27", schedule, { title: "Вторник, 1-я неделя", week_doubt: true }), 2);
});

test("общее с ботом домашки: groupDay и shortText", () => {
  const z = A.zamenaForGroup({ all_changes: { "11-А": [{ lessons: [1, 2], time: null, subject: "Отменить", room: "", uncertain: true }] }, ocr_ok: true }, "11-А");
  const ag = A.groupDay("2026-10-26", schedule, bells, z, null, "2027-01-11");
  assert.strictEqual(A.shortText(ag, z), "Информатика (возможно, отменена), Математика, География. Замены распознаны неуверенно — сверьтесь с картинкой на сайте.");
  const holiday = A.groupDay("2026-11-04", schedule, bells, null, { kind: "holiday", reason: "День народного единства" }, "2027-01-11");
  assert.strictEqual(A.shortText(holiday, null), "пар нет — День народного единства.");
  const after = A.groupDay("2027-01-12", schedule, bells, null, null, "2027-01-11");
  assert.ok(after.expired && /нового семестра/.test(A.shortText(after, null)));
});

test("данные давно не обновлялись", () => {
  const st = { checked_at: "2026-10-31T15:49+03:00" };
  assert.strictEqual(A.staleSince(st, new Date("2026-10-31T17:00:00+03:00")), "");
  assert.strictEqual(A.staleSince(st, new Date("2026-10-31T19:30:00+03:00")), "31.10 в 15:49");
  assert.strictEqual(A.staleSince({ checked_at: "2026-10-31T21:47+03:00" }, new Date("2026-11-01T07:30:00+03:00")), "");  // ночь — проверок нет
});
