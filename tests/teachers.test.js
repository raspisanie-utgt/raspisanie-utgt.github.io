// node --test tests/teachers.test.js
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");
const T = require("../site/teachers.js");

const root = path.join(__dirname, "..");
const read = (p) => JSON.parse(fs.readFileSync(path.join(root, p), "utf8"));
const bells = read("tests/fixtures/data/bells.json"), cal = read("tests/fixtures/data/calendar.json");
const schedules = read("tests/fixtures/data/groups/index.json").groups.map((g) => ({ group: g.group, schedule: read("tests/fixtures/data/groups/" + g.file) }));
const at = (hhmm) => +hhmm.slice(0, 2) * 60 + +hhmm.slice(3);

test("Трудова во вторник 27.10 в 11:00 — урок у 11-В в 1-8, дальше 11-Л", () => {
  const r = T.whereIs("Трудова С.В.", "2026-10-27", at("11:00"), schedules, bells, cal, null);
  assert.deepStrictEqual([r.now.group, r.now.room, r.now.endText], ["11-В", "1-8", "12:10"]);
  assert.ok(r.lessons.length >= 2);
});

test("после последней пары — ни сейчас, ни дальше", () => {
  const r = T.whereIs("Трудова С.В.", "2026-10-27", at("20:00"), schedules, bells, cal, null);
  assert.strictEqual(r.now, null);
  assert.strictEqual(r.next, null);
});

test("в праздник пар нет", () => {
  const r = T.whereIs("Трудова С.В.", "2026-11-04", at("11:00"), schedules, bells, cal, null);
  assert.deepStrictEqual(r.lessons, []);
});

test("подгруппы: у Хаменевой во вторник 1 пара 21-С в своём кабинете 1-14", () => {
  const r = T.whereIs("Хаменева И.И.", "2026-10-27", at("09:30"), schedules, bells, cal, null);
  assert.ok(r.now, "должна быть пара");
  assert.strictEqual(r.now.room, "1-14");
});

test("ё/е в фамилии не мешает", () => {
  const a = T.whereIs("Черных С.С.", "2026-10-26", at("10:00"), schedules, bells, cal, null);
  assert.ok(a.lessons.length > 0);
});

// замороженные образцы, а не живые data/zameny: оттуда дни старше 21 дня удаляются
const zam = (d) => { try { return read("tests/fixtures/zameny/" + d + ".json"); } catch (e) { return null; } };
const forGroup = (z) => (g) => z ? Object.assign({}, z, { changes: (z.all_changes || {})[g] || [] }) : null;

test("день преподавателя: пары по времени, у каждой группа и кабинет", () => {
  const d = T.day("Трудова С.В.", "2026-10-27", schedules, bells, cal, null);
  assert.ok(d.items.length >= 2);
  d.items.forEach((x, i) => {
    assert.ok(x.groups.length >= 1 && x.subject && x.startText);
    if (i) assert.ok(d.items[i - 1].start <= x.start);
  });
});

test("замена без преподавателя приписывается тому, кто ведёт этот предмет у группы", () => {
  // 27.10: 11-Л 7-8 «Литература» 2-18 — литературу у 11-Л ведёт Изъюрова
  const d = T.day("Изъюрова Н.М.", "2026-10-27", schedules, bells, cal, forGroup(zam("2026-10-27")));
  const l = d.items.find((x) => x.groups.includes("11-Л") && x.startText === "14:30");
  assert.ok(l, "пара по замене должна быть у Изъюровой");
  assert.ok(l.guessed && l.changed);
  assert.deepStrictEqual(l.rooms, ["2-18"]);
});

test("снятая заменой пара попадает в removed", () => {
  // 27.10: 31-Д 3-4 «Отменить»
  const z = forGroup(zam("2026-10-27"));
  const all = T.list(schedules).map((t) => [t, T.day(t, "2026-10-27", schedules, bells, cal, z).removed]);
  assert.ok(all.some(([, r]) => r.some((x) => x.group === "31-Д" && x.startText === "10:40")));
});

test("список преподавателей", () => {
  const l = T.list(schedules);
  assert.ok(l.length >= 25 && l.includes("Рыжикова Т.П."));
});

test("предмет замены сопоставляется с опечатками и по языку", () => {
  assert.ok(T.sameSubject("Техническая эксплуатация железных дорог и безопасность движения",
    "Техническая эксплуатация железных дорог и безопансость движения"));
  assert.ok(T.sameSubject("Иностранный язык в профессиональной деятельности (немецкий)", "Иностранный язык (немецкий)"));
  assert.ok(!T.sameSubject("Иностранный язык (немецкий)", "Иностранный язык (английский)"));
  assert.ok(!T.sameSubject("Математика", "Информатика"));
  assert.ok(!T.sameSubject("Русский язык", "Иностранный язык (английский)"));
});
