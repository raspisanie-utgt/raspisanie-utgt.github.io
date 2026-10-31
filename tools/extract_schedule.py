"""Извлекает расписание ВСЕХ групп очного отделения из PDF техникума
по сетке таблицы (текстовый слой PDF + линии ячеек).

    python tools/extract_schedule.py rasp.pdf            # -> data/groups/*.json
    python tools/extract_schedule.py rasp.pdf --print 21-С

Формат файла группы — как data/groups/11a.json. Ячейка, разделённая чертой
внутри пары, = чередование недель: верх — 1-я неделя, низ — 2-я.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "groups"
SOURCE = "https://utgt-pgups.ru/images/Raspisanie%20ucebnyh%20zanatij%201%20semestr%202026-2027.pdf"
VALID_TO = "2027-01-11"  # расписание 1-го семестра — до конца зимних каникул
GROUP_RE = re.compile(r"^[1-4]1-[А-ЯЁ]$")
NAME_RE = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?$")
TAIL_NAME_RE = re.compile(r"\s([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s[А-ЯЁ]\.\s?[А-ЯЁ]\.?)$")
INITIALS_RE = re.compile(r"^[А-ЯЁ]\.\s?[А-ЯЁ]\.?$")
SURNAME_END_RE = re.compile(r"\s([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]+)?)$")
ROOM_RE = re.compile(r"\d-\d{1,2}")
DAYS = 6
# Группы, которые человек сверил с PDF целиком (все 19 — 27.10.2026, расписание 1 семестра 2026/27)
VERIFIED = {"11-П", "11-Д", "11-А", "11-С", "11-В", "11-Л", "21-П", "21-Д", "21-А", "21-С", "21-Л",
            "31-П", "31-Д", "31-А", "31-С", "41-П", "41-Д", "41-А", "41-С"}


def _dark(color):
    vals = color if isinstance(color, (list, tuple)) else [color]
    return all(isinstance(v, (int, float)) and v < 0.5 for v in vals) if vals else False


def _visible(e):
    """Настоящая линия таблицы, а не край белой заливки ячейки."""
    if e.get("stroke") and _dark(e.get("stroking_color", 0)):
        return True
    return bool(e.get("fill")) and _dark(e.get("non_stroking_color", 1))


def _lines(chars):
    """Символы -> строки текста сверху вниз: [(top, text, bold_share)]."""
    rows = {}
    for c in chars:
        rows.setdefault(round(c["top"], 1), []).append(c)
    out = []
    for top in sorted(rows):
        cs = sorted(rows[top], key=lambda c: c["x0"])
        text = ""
        for prev, c in zip([None] + cs, cs):
            if prev is not None and c["x0"] - prev["x1"] > 0.35 and not text.endswith(" "):
                text += " "
            text += c["text"]
        text = " ".join(text.split())
        if text:
            bold = sum("Bold" in c["fontname"] for c in cs) / len(cs)
            out.append((top, text, bold))
    return out


def parse_cell(lines):
    """Строки ячейки -> (предмет, преподаватель). Пустая/прочерк -> None."""
    subj, teachers = [], []
    for _, text, bold in lines:
        if set(text) <= set("_- "):
            continue
        tail = TAIL_NAME_RE.search(text)
        initials = INITIALS_RE.match(text)
        if NAME_RE.match(text):
            teachers.append(text)
        elif tail and subj:  # «... телемеханики Добряков Ю.В.» или «тр.-та) Марчак А.В.» в одной строке
            subj.append(text[:tail.start()].strip())
            teachers.append(tail.group(1))
        elif initials and subj and SURNAME_END_RE.search(subj[-1]):
            # фамилия в конце строки, инициалы перенеслись: «... автом. Добряков» + «Ю.В.»
            m = SURNAME_END_RE.search(subj[-1])
            subj[-1] = subj[-1][:m.start()].strip()
            teachers.append(f"{m.group(1)} {text}")
        elif bold > 0.6 and subj and len(text) < 30:
            teachers.append(text)
        else:
            subj.append(text)
    if not subj:
        return None
    # подгруппы: «предмет, преподаватель, предмет, преподаватель» в одной ячейке (англ. / нем.)
    parts = [" ".join(subj)]
    if len(teachers) > 1:
        groups, cur = [], []
        for _, text, _ in lines:
            if text in teachers:
                if cur:
                    groups.append(" ".join(cur))
                cur = []
            elif text in subj:
                cur.append(text)
        if len(groups) == len(teachers):
            parts = groups
    subject = " / ".join(re.sub(r"(\w\.?)- (\w)", r"\1-\2", p) for p in parts)  # перенос «рем.- регулир...»
    return subject, " / ".join(teachers)


class Sheet:
    def __init__(self, page):
        self.p = page
        self.chars = page.chars
        self.h = [e for e in page.horizontal_edges if e["width"] > 3 and _visible(e)]
        self.v = [e for e in page.vertical_edges if e["height"] > 3 and _visible(e)]
        self._columns()
        self._rows()

    def _columns(self):
        heads = [w for w in self.p.extract_words() if GROUP_RE.match(w["text"]) and w["top"] < 45]
        xs = sorted({round(e["x0"], 1) for e in self.v if e["height"] > 20})
        merged = []
        for x in xs:  # двойные линии -> одна
            if not merged or x - merged[-1] > 1:
                merged.append(x)
        self.groups = {}
        for w in sorted(heads, key=lambda w: w["x0"]):
            left = max(x for x in merged if x < w["x0"] - 2)
            nxt = [x for x in merged if x > w["x1"] + 2]
            room = nxt[0]
            right = nxt[1] if len(nxt) > 1 else self.p.width
            self.groups[w["text"]] = (left, room, right)

    def _rows(self):
        lesson_col = (6.4, 11.0)
        nums = [w for w in self.p.within_bbox((lesson_col[0], 40, lesson_col[1], self.p.height))
                .extract_words(x_tolerance=1.5) if w["text"].isdigit()]
        nums.sort(key=lambda w: w["top"])
        seps = sorted({round(e["top"], 1) for e in self.h
                       if e["x0"] <= lesson_col[0] + 1 and e["x1"] >= lesson_col[1] - 1})
        self.days, day = [], []
        for w in nums:
            n = int(w["text"])
            if n == 1 and day:
                self.days.append(day)
                day = []
            day.append((n, w["top"]))
        self.days.append(day)
        assert len(self.days) == DAYS, f"нашлось дней: {len(self.days)}"
        self.pairs = []  # [(день 1..6, номер пары, y_top, y_bot)]
        for d, day in enumerate(self.days, 1):
            tops = dict(day)
            for k in range(1, 6):
                t1, t2 = tops[2 * k - 1], tops[2 * k]
                y0 = max(s for s in seps if s < t1)
                y1 = min(s for s in seps if s > t2)
                self.pairs.append((d, k, y0, y1))
        self.monday_top = self.pairs[0][2]

    def text_in(self, x0, x1, y0, y1):
        return _lines([c for c in self.chars
                       if x0 <= (c["x0"] + c["x1"]) / 2 < x1 and y0 < (c["top"] + c["bottom"]) / 2 < y1])

    def split_y(self, x0, x1, y0, y1):
        """Черта внутри пары по всей ширине колонки предмета -> её y, иначе None."""
        for e in self.h:
            if y0 + 1.5 < e["top"] < y1 - 1.5 and e["x0"] <= x0 + 2 and e["x1"] >= x1 - 2:
                return e["top"]
        return None

    def has_left_border(self, x, y0, y1):
        return any(abs(e["x0"] - x) < 1 and e["top"] <= y0 + 2 and e["bottom"] >= y1 - 2 for e in self.v)

    def group(self, name):
        left, room_x, right = self.groups[name]
        days = {str(d): [] for d in range(1, DAYS + 1)}
        warnings = []
        # «Разговоры о важном» над первой парой понедельника
        top_text = " ".join(t for _, t, _ in self.text_in(left, right, 45, self.monday_top))
        if "Разговор" in top_text:
            days["1"].append({"lessons": [0], "subject": "Разговоры о важном", "teacher": "", "room": ""})
        for d, k, y0, y1 in self.pairs:
            lessons = [2 * k - 1, 2 * k]
            if not self.has_left_border(left, y0, y1):
                warnings.append(f"день {d}, пара {k}: ячейка объединена с соседней группой")
            sy = self.split_y(left, room_x, y0, y1)
            parts = [(None, y0, y1)] if sy is None else [(1, y0, sy), (2, sy, y1)]
            for week, a, b in parts:
                cell = parse_cell(self.text_in(left, room_x, a, b))
                rooms = " ".join(t for _, t, _ in self.text_in(room_x, right, a, b))
                if not cell:
                    if rooms.strip():
                        warnings.append(f"день {d}, пара {k}: кабинет без предмета")
                    continue
                subject, teacher = cell
                entry = {"lessons": lessons}
                if week:
                    entry["week"] = week
                entry.update(subject=subject, teacher=teacher, room=" / ".join(ROOM_RE.findall(rooms)) or rooms.strip())
                if not teacher:
                    warnings.append(f"день {d}, пара {k}: не найден преподаватель ({subject})")
                days[str(d)].append(entry)
        return days, warnings


LATIN = {"П": "p", "Д": "d", "А": "a", "С": "s", "В": "v", "Л": "l"}


def teacher_fixer(full_names):
    """Опечатки в инициалах (в PDF у 21-Л «Канева О.В.», а в педсоставе одна Канева — Ольга Петровна):
    если фамилия встречается в списке педсостава ровно один раз, инициалы берём оттуда."""
    by_surname = {}
    for full in full_names:
        parts = full.split()
        if len(parts) >= 3:
            by_surname.setdefault(parts[0], []).append(f"{parts[0]} {parts[1][0]}.{parts[2][0]}.")

    def fix(short):
        surname = short.split(" ")[0]
        found = by_surname.get(surname, [])
        return found[0] if len(found) == 1 else short

    def fix_days(days):
        fixed = []
        for entries in days.values():
            for e in entries:
                new = " / ".join(fix(t) for t in e["teacher"].split(" / ")) if e["teacher"] else ""
                if new != e["teacher"]:
                    fixed.append(f"{e['teacher']} -> {new}")
                    e["teacher"] = new
        return fixed
    return fix_days


WORD_RE = re.compile(r"[А-ЯЁа-яё]{6,}")
CODE_DOT_RE = re.compile(r"^((?:МДК|ПМ|ОП|ОГСЭ|ЕН)\.\d+(?:\.\d+)?)\.(?=\s)")


def subject_fixer(all_days):
    """Опечатки-перестановки в названиях предметов («безопансость», «устрйоств»): слово, которое
    встречается один раз и состоит из тех же букв, что и более частое слово, заменяется им.
    И «МДК.02.02. Название» -> «МДК.02.02 Название» (точка после кода то есть, то нет)."""
    count = {}  # слово в нижнем регистре -> сколько раз встречается
    for days in all_days:
        for entries in days.values():
            for e in entries:
                for w in WORD_RE.findall(e["subject"]):
                    count[w.lower()] = count.get(w.lower(), 0) + 1
    by_letters = {}
    for w, n in count.items():
        by_letters.setdefault("".join(sorted(w)), []).append((n, w))
    fix = {}  # опечатка (нижний регистр) -> верное слово (нижний регистр)
    for words in by_letters.values():
        if len(words) < 2:
            continue
        words.sort(reverse=True)
        for n, w in words[1:]:
            if n < words[0][0]:
                fix[w] = words[0][1]

    def repl(m):
        w = m.group(0)
        good = fix.get(w.lower())
        if not good:
            return w
        return good[0].upper() + good[1:] if w[0].isupper() else good

    def fix_days(days):
        fixed = []
        for entries in days.values():
            for e in entries:
                new = WORD_RE.sub(repl, e["subject"])
                new = " / ".join(CODE_DOT_RE.sub(r"\1", x) for x in new.split(" / "))
                if new != e["subject"]:
                    fixed.append(f"{e['subject']} -> {new}")
                    e["subject"] = new
        return fixed
    return fix_days


def apply_popravki(name, days, popravki):
    """Ручные поправки (data/popravki.json): переименования предметов и правки отдельных пар."""
    done = []
    names = popravki.get("subjects", {})
    for entries in days.values():
        for e in entries:
            new = " / ".join(names.get(x, x) for x in e["subject"].split(" / "))
            if new != e["subject"]:
                done.append(f"{e['subject']} -> {new}")
                e["subject"] = new
    for p in popravki.get("entries", []):
        if p["group"] != name:
            continue
        for e in days.get(p["day"], []):
            if e["lessons"] == p["lessons"]:
                e.update(p["set"])
                if p.get("note"):
                    e["note"] = p["note"]
                done.append(f"{p['day']} {p['lessons']}: {p['set']}")
    return done


def group_slug(name):
    """«11-А» -> «11a» (латиница для имён файлов и ссылок)."""
    return name[:2] + LATIN.get(name[-1], name[-1].lower())


def build_group_file(name, days, warnings):
    return {
        "group": name,
        "source": SOURCE,
        "title": "Расписание учебных занятий на 1 семестр 2026/2027 учебного года (очное отделение)",
        "note": "Извлечено автоматически tools/extract_schedule.py. week: 1/2 — пара только в эту неделю.",
        "week_anchor": {"date": "2026-10-19", "week": 1},
        "verified": name in VERIFIED,
        "warnings": warnings,
        "days": days,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--print", dest="show")
    args = ap.parse_args()
    sheet = Sheet(pdfplumber.open(args.pdf).pages[0])
    if args.show:
        days, warnings = sheet.group(args.show)
        print(json.dumps({"days": days, "warnings": warnings}, ensure_ascii=False, indent=1))
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    teachers = ROOT / "data" / "teachers.json"
    fix_days = teacher_fixer(json.loads(teachers.read_text(encoding="utf-8"))["teachers"] if teachers.exists() else [])
    index = []
    parsed = {name: sheet.group(name) for name in sheet.groups}
    fix_subjects = subject_fixer([days for days, _ in parsed.values()])
    pop_path = ROOT / "data" / "popravki.json"
    popravki = json.loads(pop_path.read_text(encoding="utf-8")) if pop_path.exists() else {}
    for name in sheet.groups:
        days, warnings = parsed[name]
        for f in fix_days(days):
            print(f"{name}: исправлены инициалы {f}")
        for f in fix_subjects(days):
            print(f"{name}: исправлен предмет {f}")
        for f in apply_popravki(name, days, popravki):
            print(f"{name}: ручная поправка {f}")
        slug = group_slug(name)
        data = build_group_file(name, days, warnings)
        (OUT / f"{slug}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        n = sum(len(v) for v in days.values())
        index.append({"group": name, "file": f"{slug}.json", "course": int(name[0]), "verified": name in VERIFIED,
                      "pairs": n, "warnings": len(warnings)})
        print(f"{name}: {n} записей, предупреждений: {len(warnings)}")
    # до какого дня действует расписание (конец зимних каникул) — после сайт пишет «нового расписания ещё нет»,
    # а не показывает старое; при новом семестре поменять VALID_TO вместе с SOURCE
    (OUT / "index.json").write_text(json.dumps({"source": SOURCE, "valid_to": VALID_TO, "groups": index}, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
