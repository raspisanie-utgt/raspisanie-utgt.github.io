// node --test tests/calendar.test.js
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const fs = require("node:fs");
const C = require("../site/calendar.js");

const cal = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/data/calendar.json"), "utf8"));
const G = "11-А";
const texts = (d) => C.countdown(d, cal, G).map((l) => l.text);

test("склонение дней", () => {
  assert.deepStrictEqual([1, 2, 5, 11, 21, 22, 63, 112].map(C.daysText),
    ["1 день", "2 дня", "5 дней", "11 дней", "21 день", "22 дня", "63 дня", "112 дней"]);
});

test("оставшееся время: больше часа — часы и минуты", () => {
  assert.deepStrictEqual([1, 5, 40, 60, 61, 85, 90, 125].map(C.minutesText),
    ["1 минута", "5 минут", "40 минут", "1 час", "1 час 1 минута", "1 час 25 минут", "1 час 30 минут", "2 часа 5 минут"]);
});

test("27 октября: до зимних каникул и ближайший праздник", () => {
  assert.deepStrictEqual(texts("2026-10-27"), [
    "До каникул 63 дня (с 29 декабря)",
    "4 ноября выходной — День народного единства",
  ]);
  assert.deepStrictEqual(texts("2026-11-03"), ["До каникул 56 дней (с 29 декабря)", "Завтра выходной — День народного единства"]);
});

test("строка под датой: коротко, за неделю — «осталось», выходной — коротко; полоска", () => {
  const short = (d) => C.countdown(d, cal, G).map((l) => l.short);
  assert.deepStrictEqual(short("2026-10-27"), ["До каникул 63 дня", "4 ноября выходной"]);
  assert.deepStrictEqual(short("2026-11-03"), ["До каникул 56 дней", "Завтра выходной"]);
  assert.deepStrictEqual(short("2026-12-21")[0], "До каникул 8 дней");
  assert.deepStrictEqual(short("2026-12-22")[0], "До каникул осталось 7 дней");
  assert.deepStrictEqual(short("2026-12-28")[0], "До каникул остался 1 день");
  assert.deepStrictEqual(short("2027-01-05")[0], "Зимние каникулы — ещё 6 дней");
  const pr = (d) => C.countdown(d, cal, G)[0].progress;
  assert.strictEqual(pr("2026-09-01"), 0);
  assert.ok(Math.abs(pr("2026-10-29") - 58 / 119) < 1e-9);       // 1 сентября → 29 декабря
  assert.ok(pr("2026-12-28") > 0.99 && pr("2026-12-28") < 1);
  assert.ok(Math.abs(pr("2027-01-05") - 8 / 14) < 1e-9);          // каникулы 29.12–11.01
  assert.ok(Math.abs(pr("2027-01-12") - 0) < 1e-9);               // после зимних — с начала до летних
});

test("праздники и каникулы — занятий нет", () => {
  assert.deepStrictEqual(C.dayOff("2026-11-04", cal, G), { kind: "holiday", reason: "День народного единства" });
  assert.strictEqual(C.dayOff("2027-01-05", cal, G).reason, "Зимние каникулы");
  assert.strictEqual(C.dayOff("2027-01-05", cal, G).until, "2027-01-11");
  assert.strictEqual(C.dayOff("2026-12-28", cal, G), null);
  assert.strictEqual(C.dayOff("2027-01-12", cal, G), null);
});

test("во время каникул — сколько осталось, без «до каникул»", () => {
  assert.deepStrictEqual(texts("2027-01-05")[0], "Зимние каникулы до 11 января — ещё 6 дней");
  assert.deepStrictEqual(texts("2027-01-11")[0], "Зимние каникулы до 11 января — последний день");
  assert.ok(!texts("2027-01-05").some((t) => t.startsWith("До каникул")));
});

test("за 45 дней до сессии — отсчёт и экзамены", () => {
  assert.ok(!texts("2027-05-01").some((t) => t.startsWith("До сессии")));
  const lines = C.countdown("2027-05-20", cal, G);
  const s = lines.find((l) => l.kind === "sessiya");
  assert.strictEqual(s.text, "До сессии 35 дней (с 24 июня)");
  assert.strictEqual(s.exams.length, 4);
});

test("другая группа без данных — пусто, без ошибок", () => {
  assert.deepStrictEqual(C.countdown("2026-10-27", { holidays: [] }, "99-Я"), []);
  assert.strictEqual(C.dayOff("2026-10-27", {}, "99-Я"), null);
});

test("учебная часть: открыто, обед, закрыто, праздник", () => {
  const office = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/data/info.json"), "utf8")).office;
  const st = (d, hhmm) => C.officeStatus(d, +hhmm.slice(0, 2) * 60 + +hhmm.slice(3), office, cal).text;
  assert.strictEqual(st("2026-10-27", "10:00"), "Открыто до 16:30");
  assert.strictEqual(st("2026-10-27", "11:45"), "Обед до 12:00");
  assert.strictEqual(st("2026-10-27", "07:50"), "Закрыто, откроется сегодня в 08:30");
  assert.strictEqual(st("2026-10-27", "17:00"), "Закрыто, откроется завтра в 08:30");
  assert.strictEqual(st("2026-10-31", "14:59"), "Открыто до 15:00");          // суббота
  assert.strictEqual(st("2026-10-31", "15:30"), "Закрыто, откроется 2 ноября в 08:30"); // воскресенье пропускаем
  assert.strictEqual(st("2026-11-03", "18:00"), "Закрыто, откроется 5 ноября в 08:30"); // 4 ноября праздник
  assert.strictEqual(C.officeStatus("2026-10-27", 600, office, cal).open, true);
});

test("текущий период графика: сессия 31-Д 25.12", () => {
  const cal = JSON.parse(require("node:fs").readFileSync(require("node:path").join(__dirname, "..", "data", "calendar.json"), "utf8"));
  assert.strictEqual(C.current("2026-12-25", cal, "31-Д").type, "sessiya");
  assert.strictEqual(C.current("2026-10-27", cal, "31-Д"), null);
});

test("за пределами учебного графика — государственные праздники всё равно знаем", () => {
  const cal = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "fixtures/data/calendar.json"), "utf8"));
  assert.strictEqual(C.dayOff("2027-11-04", cal, "11-А").reason, "День народного единства");
  assert.strictEqual(C.dayOff("2028-01-03", cal, "11-А").kind, "holiday");
  assert.strictEqual(C.dayOff("2027-11-05", cal, "11-А"), null);
  assert.strictEqual(C.dayOff("2026-11-05", cal, "11-А"), null);  // внутри графика — только то, что в нём
});
