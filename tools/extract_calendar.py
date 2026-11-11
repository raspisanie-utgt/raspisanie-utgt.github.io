"""Извлекает календарный учебный график (КУГ) всех групп очного отделения из PDF
техникума: праздники, каникулы, сессию с экзаменами, практику (с названием по условным
обозначениям), учебные сборы, специальность группы и курсовые работы.

    python tools/extract_calendar.py kug.pdf             # -> data/calendar.json
    python tools/extract_calendar.py kug.pdf --print 11-А

В графике столбец = учебная неделя (вторник–понедельник), строки ВТ..ПН = дни.
Обозначения в клетках: «=» каникулы, «::» промежуточная аттестация, «СБ» учебные
сборы, «8»/«X»/«0…» практика, «˄» подготовка к демоэкзамену, «э» демоэкзамен,
«В» выходной (в будний день — праздник).
"""
import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "https://utgt-pgups.ru/images/Svodnyj%20KUG%20ocnoe%20otdelenie%202026-2027%20ucebnyj%20god.pdf"
YEAR_START = dt.date(2026, 9, 1)  # 1 сентября — первый день недели №1 (в 2026 — вторник)
WEEKDAYS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
DAYS = ["ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС", "ПН"]  # строки графика: с дня недели 1 сентября
YEAR_RE = re.compile(r"НА\s+(20\d\d)\s*[-–/]\s*(20\d\d)\s+УЧЕБН", re.I)


def configure(year, source):
    """Учебный год графика: неделя №1 начинается 1 сентября, строки дней — с его дня недели."""
    global YEAR_START, DAYS, SOURCE
    YEAR_START = dt.date(year, 9, 1)
    k = YEAR_START.weekday()
    DAYS = WEEKDAYS[k:] + WEEKDAYS[:k]
    SOURCE = source


def pdf_year(pdf_path):
    """Первый год учебного года по заголовку PDF («НА 2026 - 2027 УЧЕБНЫЙ ГОД» -> 2026) или None."""
    with pdfplumber.open(pdf_path) as pdf:
        text = " ".join((pdf.pages[0].extract_text() or "").split())
    m = YEAR_RE.search(text)
    return int(m.group(1)) if m and int(m.group(2)) == int(m.group(1)) + 1 else None
GROUP_RE = re.compile(r"^[1-4]1-[А-ЯЁ]$")
HOLIDAY_NAMES = {(11, 4): "День народного единства", (2, 23): "День защитника Отечества",
                 (3, 8): "Международный женский день", (5, 1): "Праздник Весны и Труда",
                 (5, 9): "День Победы", (5, 10): "День Победы (перенос с 9 мая)", (6, 12): "День России",
                 (1, 1): "Новогодние каникулы", (1, 7): "Рождество Христово"}

KINDS = {"=": "kanikuly", "::": "sessiya", "СБ": "sbory", "8": "praktika", "X": "praktika", "Х": "praktika",
         "˄": "demo_prep", "^": "demo_prep", "э": "demo", "Э": "demo"}
NAMES = {"sessiya": "Сессия", "sbory": "Учебные сборы (юноши)", "praktika": "Практика",
         "demo_prep": "Подготовка к демоэкзамену", "demo": "Демоэкзамен"}
PRACTICE_NAMES = {"8": "Производственная практика (по профилю специальности)",
                  "X": "Производственная практика (технологическая)", "Х": "Производственная практика (технологическая)"}
SPECIALTY_RE = re.compile(r"^\d\d\.\d\d\.\d\d$")
LEGEND_CODE_RE = re.compile(r"^0[а-яё]+$")
ROMAN_RE = re.compile(r"^[IVХ]+$|^[IV]+(?=[а-яё(])|(?<=[а-яё)])[IV]+$")  # номер курса, прилипший к слову
WORD_ENDINGS = {"ом", "ого", "ного", "ной", "ных", "ния", "ние", "ия", "ой", "ых", "ая"}
SEASON = ["Зимние", "Весенние", "Летние", "Осенние"]  # по месяцу начала: 12–2, 3–5, 6–8, 9–11
NO_CLASSES = {"kanikuly", "sbory", "praktika", "demo_prep", "demo"}


def kind_of(text):
    if text in KINDS:
        return KINDS[text]
    if re.match(r"^0[а-яё]", text):  # учебная практика: 0мсцб, 0эмр, …
        return "praktika"
    return None


class Page:
    def __init__(self, page):
        self.page = page
        self.words = page.extract_words()
        self._weeks()
        self._groups()

    def _weeks(self):
        """x-центры столбцов недель 1..52 — по строке с номерами недель."""
        rows = collections.defaultdict(list)
        for w in self.words:
            if w["text"].isdigit():
                rows[round(w["top"] / 4)].append(w)
        best = max(rows.values(), key=lambda r: len({w["text"] for w in r if 1 <= int(w["text"]) <= 52}))
        xs = {}
        for w in sorted(best, key=lambda w: w["x0"]):
            n = int(w["text"])
            if 1 <= n <= 52 and n not in xs:
                xs[n] = (w["x0"] + w["x1"]) / 2
        assert len(xs) == 52, f"нашлось недель: {len(xs)}"
        self.week_x = xs
        self.step = (xs[52] - xs[1]) / 51
        self.weeks_top = best[0]["top"]
        # колонки «ЭКЗАМЕНЫ: 1 семестр | 2 семестр» — между тремя последними вертикальными линиями таблицы
        borders = []
        for x in sorted(e["x0"] for e in self.page.vertical_edges if e["x0"] > xs[52] and e["height"] > 100):
            if not borders or x - borders[-1] > 3:
                borders.append(x)
        # справа налево: экзамены 2 и 1 семестра, курсовые 2 и 1 семестра
        b = borders[-5:]
        self.course_cols = [(b[0], b[1]), (b[1], b[2])]
        self.exam_cols = [(b[2], b[3]), (b[3], b[4])]

    def _groups(self):
        labels = sorted([w for w in self.words if w["text"] in DAYS and w["top"] > self.weeks_top
                         and w["x0"] < self.week_x[1]], key=lambda w: w["top"])
        heads = [w for w in self.words if GROUP_RE.match(w["text"]) and w["x0"] < self.week_x[1]]
        self.groups = {}
        for h in heads:
            # 7 строк дней, середина которых ближе всего к подписи группы
            rows = [l for l in labels if abs(l["top"] - h["top"]) < 200]
            rows.sort(key=lambda l: l["top"])
            start = min(range(0, len(rows) - 6), key=lambda i: abs(rows[i + 3]["top"] - h["top"]))
            block = rows[start:start + 7]
            assert [l["text"] for l in block] == DAYS, (h["text"], [l["text"] for l in block])
            self.groups[h["text"]] = [l["top"] for l in block]

    def exams(self, group):
        """[[экзамены 1 семестра], [экзамены 2 семестра]] из правой части графика."""
        return self._column_items(group, self.exam_cols)

    def courseworks(self, group):
        """[[курсовые 1 семестра], [курсовые 2 семестра]]."""
        return self._column_items(group, self.course_cols)

    def specialties(self):
        """{группа: (код, название специальности)} — из левой колонки рядом с группами."""
        left = min(w["x0"] for w in self.words if GROUP_RE.match(w["text"]))
        col = [w for w in self.words if w["x1"] < left and w["top"] > self.weeks_top]
        codes = sorted((w for w in col if SPECIALTY_RE.match(w["text"])), key=lambda w: w["top"])
        bottom = min([w["top"] for w in col if w["text"].startswith("Условные")] or [self.page.height])
        blocks = []
        for i, c in enumerate(codes):
            end = codes[i + 1]["top"] if i + 1 < len(codes) else bottom
            ws = [w for w in col if c["top"] < w["top"] < end and not SPECIALTY_RE.match(w["text"])]
            lines = collections.defaultdict(list)
            for w in ws:
                lines[round(w["top"] / 5)].append(w)
            text = ""
            for _, line in sorted(lines.items()):
                for w in sorted(line, key=lambda w: w["x0"]):
                    word = ROMAN_RE.sub("", w["text"])
                    if not word:
                        continue
                    # слово, перенесённое по ширине ячейки: «(железнодорожн» + «ом»
                    last = text.split(" ")[-1]
                    glued = word in WORD_ENDINGS and len(last) >= 8 and last[-1].isalpha()
                    text += ("" if glued else " ") + word
            center = (c["top"] + max(w["top"] for w in ws)) / 2
            blocks.append((center, c["text"], " ".join(text.split())))
        out = {}
        for g, tops in self.groups.items():
            mid = (tops[0] + tops[-1]) / 2
            _, code, name = min(blocks, key=lambda b: abs(b[0] - mid))
            out[g] = (code, name)
        return out

    def legend(self):
        """Условные обозначения учебных практик: {«0мсцб»: «Учебная практика: Монтаж …»}."""
        codes = [w for w in self.words if LEGEND_CODE_RE.match(w["text"]) and w["top"] > max(
            t for tops in self.groups.values() for t in tops)]
        xs = sorted({round(c["x0"], -1) for c in codes})
        out = {}
        for c in codes:
            nxt = [x for x in xs if x > c["x0"] + 50]
            x1 = (nxt[0] - 40) if nxt else self.page.width
            ws = [w for w in self.words if c["x1"] + 20 < w["x0"] < x1 and abs(w["top"] - c["top"]) < 45]
            ws.sort(key=lambda w: (round(w["top"] / 5), w["x0"]))
            text = " ".join(" ".join(w["text"] for w in ws).split())
            if text:
                text = text[0].upper() + text[1:]
                out[c["text"]] = text if text.startswith("Учебная практика") else "Учебная практика: " + text
        return out

    def _column_items(self, group, cols):
        tops = self.groups[group]
        rowh = (tops[-1] - tops[0]) / 6
        y0, y1 = tops[0] - rowh / 2, tops[-1] + rowh / 2
        out = []
        for x0, x1 in cols:
            lines = collections.defaultdict(list)
            for w in self.words:
                if x0 <= w["x0"] < x1 and y0 <= w["top"] < y1:
                    lines[round(w["top"] / 3)].append(w)
            text = " ".join(" ".join(x["text"] for x in sorted(ws, key=lambda x: x["x0"]))
                            for _, ws in sorted(lines.items()))
            items = [" ".join(t.split()).strip(" .") for t in text.split(";")]
            out.append([t for t in items if len(t) > 2])
        return out

    def cells(self, group):
        """{дата: обозначение} для группы."""
        tops = self.groups[group]
        rowh = (tops[-1] - tops[0]) / 6
        out = {}
        for w in self.words:
            cx = (w["x0"] + w["x1"]) / 2
            if cx < self.week_x[1] - self.step / 2 or cx > self.week_x[52] + self.step / 2:
                continue
            day = min(range(7), key=lambda i: abs(tops[i] - w["top"]))
            if abs(tops[day] - w["top"]) > rowh / 2:
                continue
            week = min(self.week_x, key=lambda n: abs(self.week_x[n] - cx))
            if abs(self.week_x[week] - cx) > self.step / 2:
                continue
            date = YEAR_START + dt.timedelta(days=7 * (week - 1) + day)
            out[date] = w["text"]
        return out


def practice_name(text, legend):
    return legend.get(text) or PRACTICE_NAMES.get(text) or NAMES["praktika"]


def periods_from(cells, holidays, legend=None):
    """Подряд идущие дни одного вида -> периоды; воскресенья и праздники не разрывают период."""
    legend = legend or {}
    marks = sorted((d, kind_of(t), practice_name(t, legend) if kind_of(t) == "praktika" else None)
                   for d, t in cells.items() if kind_of(t))
    out = []
    for d, kind, pname in marks:
        last = out[-1] if out else None
        if last and last["type"] == kind and last.get("_pname") == pname:
            gap = (d - last["to"]).days
            between = [last["to"] + dt.timedelta(days=i) for i in range(1, gap)]
            if gap <= 3 and all(x.isoweekday() == 7 or x in holidays or cells.get(x) == "В" for x in between):
                last["to"] = d
                continue
        out.append({"type": kind, "from": d, "to": d, "_pname": pname})
    year_end = YEAR_START + dt.timedelta(days=7 * 52 - 1)  # понедельник последней недели графика
    for p in out:
        if p["to"] == year_end:
            p["to"] = YEAR_START.replace(year=YEAR_START.year + 1) - dt.timedelta(days=1)  # до 31 августа
        pname = p.pop("_pname")
        if p["type"] == "kanikuly":
            p["name"] = SEASON[(p["from"].month % 12) // 3] + " каникулы"
        else:
            p["name"] = pname or NAMES[p["type"]]
        if p["type"] in NO_CLASSES:
            p["no_classes"] = True
    return out


def extract(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        pages = [Page(p) for p in pdf.pages]
        all_cells = {g: pg.cells(g) for pg in pages for g in pg.groups}
        all_exams = {g: pg.exams(g) for pg in pages for g in pg.groups}
        all_courseworks = {g: pg.courseworks(g) for pg in pages for g in pg.groups}
        specialty = {g: s for pg in pages for g, s in pg.specialties().items()}
        legend = {}
        for pg in pages:
            legend.update(pg.legend())
    # праздник = «В» в будний день у большинства групп
    votes = collections.Counter(d for c in all_cells.values() for d, t in c.items()
                                if t == "В" and d.isoweekday() != 7)
    holidays = sorted(d for d, n in votes.items() if n >= len(all_cells) / 2)
    groups = {}
    for g, cells in sorted(all_cells.items()):
        ps = periods_from(cells, set(holidays), legend)
        sessions = [p for p in ps if p["type"] == "sessiya"]
        for sem, exams in enumerate(all_exams[g]):
            # 1 семестр — сессия до февраля, 2 семестр — последняя сессия года
            target = [p for p in sessions if p["from"].month >= 9 or p["from"].month <= 1] if sem == 0 else sessions[-1:]
            if exams and target:
                target[0]["exams"] = exams
        code, name = specialty[g]
        groups[g] = {"specialty": {"code": code, "name": name},
                     "courseworks": {str(i + 1): c for i, c in enumerate(all_courseworks[g]) if c},
                     "periods": [{**p, "from": p["from"].isoformat(), "to": p["to"].isoformat()} for p in ps]}
    return {
        "source": SOURCE,
        "title": f"Сводный календарный учебный график на {YEAR_START.year}-{YEAR_START.year + 1} учебный год (очная форма обучения)",
        "note": "Извлечено tools/extract_calendar.py. type: kanikuly / sessiya / sbory / praktika / demo_prep / demo.",
        "holidays": [{"date": d.isoformat(), "name": HOLIDAY_NAMES.get((d.month, d.day), "Праздничный день")}
                     for d in holidays],
        "groups": groups,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--print", dest="show")
    ap.add_argument("--out", default=str(ROOT / "data" / "calendar.json"))
    args = ap.parse_args()
    cal = extract(args.pdf)
    if args.show:
        print(json.dumps({"holidays": cal["holidays"], **cal["groups"][args.show]}, ensure_ascii=False, indent=1))
        return 0
    Path(args.out).write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    for g, v in cal["groups"].items():
        print(g, "; ".join(f"{p['name']} {p['from'][5:]}–{p['to'][5:]}" for p in v["periods"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
