"""Проверка данных на подозрительные места: опечатки, накладки, странные кабинеты, сомнительные замены.

    python tools/check_data.py          # отчёт; код выхода 1, если есть ошибки (не предупреждения)

Ошибка — то, что почти наверняка неверно (пара без предмета, кабинет не того вида, накладка
пар в одной группе). Предупреждение — то, что стоит проверить глазами (похожие названия,
один кабинет у двух пар, преподаватель в двух местах).
"""
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ROOM_RE = re.compile(r"^([12]-(\d{1,2}[А-ЯЁ]?|\?)|\?)$")  # «2-1Е» — есть такой; «?» / «2-?» — кабинет на уточнении
# кабинеты без номера (если появятся) — из data/rooms.json
NAMED_ROOMS = set(json.loads((ROOT / "data" / "rooms.json").read_text(encoding="utf-8")).get("rooms", {}))
TEACHER_RE = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)? [А-ЯЁ]\.[А-ЯЁ]\.$")
DAYS = {"1": "пн", "2": "вт", "3": "ср", "4": "чт", "5": "пт", "6": "сб"}


def load_groups():
    index = json.loads((DATA / "groups" / "index.json").read_text(encoding="utf-8"))
    return {g["group"]: json.loads((DATA / "groups" / g["file"]).read_text(encoding="utf-8")) for g in index["groups"]}


def parts(e, key):
    return [x.strip() for x in str(e.get(key) or "").split(" / ")]


def words(s):
    return re.findall(r"[а-яёa-z]+", s.lower())


def similar_names(names, threshold=0.93):
    """Почти одинаковые названия с одним и тем же кодом (или без кода): «…устрйоств…» / «…устройств…»."""
    out = []
    code = lambda n: (re.match(r"^((?:МДК|ПМ|ОП)\.[\d.]+)", n) or [None, ""])[1].rstrip(".")
    for a, b in combinations(sorted(names), 2):
        if a.lower() == b.lower() or code(a) != code(b):
            continue
        if SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold:
            out.append((a, b))
    return out


def typo_words(names):
    """Слова-перестановки: «безопансость» при «безопасность» в других названиях."""
    count = defaultdict(int)
    for n in names:
        for w in words(n):
            if len(w) >= 6:
                count[w] += 1
    by_letters = defaultdict(list)
    for w in count:
        by_letters["".join(sorted(w))].append(w)
    return [(a, b) for ws in by_letters.values() for a, b in combinations(sorted(ws), 2)]


def check_schedules(groups, staff):
    errors, warnings = [], []
    subjects, teachers = set(), defaultdict(set)
    by_slot = defaultdict(list)  # (день, урок, неделя) -> [(группа, предмет, преподаватель, кабинет)]
    for g, s in groups.items():
        for day, entries in s["days"].items():
            taken = {}
            for e in entries:
                where = f"{g} {DAYS.get(day, day)} уроки {e['lessons']}"
                if e["lessons"] == [0]:
                    continue
                if not e["subject"].strip():
                    errors.append(f"{where}: пустой предмет")
                if len(e["lessons"]) != 2 or e["lessons"][0] % 2 != 1 or e["lessons"][1] != e["lessons"][0] + 1:
                    warnings.append(f"{where}: необычные номера уроков")
                for n in e["lessons"]:
                    for w in ([e.get("week")] if e.get("week") else [1, 2]):
                        if (n, w) in taken:
                            errors.append(f"{where}: накладка с «{taken[(n, w)]}»")
                        taken[(n, w)] = e["subject"]
                subj, teach, rooms = parts(e, "subject"), parts(e, "teacher"), parts(e, "room")
                for r in rooms:
                    if not ROOM_RE.match(r):
                        errors.append(f"{where}: странный кабинет «{r}»")
                for t in teach:
                    if not TEACHER_RE.match(t):
                        errors.append(f"{where}: странное имя преподавателя «{t}»")
                    elif staff and t not in staff:
                        warnings.append(f"{where}: «{t}» нет в списке педсостава")
                for i, sj in enumerate(subj):
                    subjects.add(sj)
                    t = teach[i] if i < len(teach) else teach[0]
                    r = rooms[i] if i < len(rooms) else rooms[0]
                    teachers[t.split(" ")[0]].add(t)
                    for w in ([e.get("week")] if e.get("week") else [1, 2]):
                        by_slot[(day, e["lessons"][0], w)].append((g, sj, t, r))
    # одна фамилия с разными инициалами
    for surname, names in teachers.items():
        if len(names) > 1:
            warnings.append(f"преподаватель с разными инициалами: {', '.join(sorted(names))}")
    # кабинет занят двумя разными парами / преподаватель в двух местах
    seen = set()
    for (day, n, w), rows in sorted(by_slot.items()):
        when = f"{DAYS[day]} {(n + 1) // 2}-я пара"
        rooms, places = defaultdict(set), defaultdict(set)
        for g, sj, t, r in rows:
            rooms[r].add((t, sj))
            places[t].add(r)
        for r, who in rooms.items():
            if len({t for t, _ in who}) > 1:
                key = ("room", day, n, r)
                if key not in seen:
                    seen.add(key)
                    warnings.append(f"{when}: в {r} сразу {', '.join(sorted(t for t, _ in who))}")
        for t, rs in places.items():
            if len(rs) > 1:
                key = ("teacher", day, n, t)
                if key not in seen:
                    seen.add(key)
                    warnings.append(f"{when}: {t} одновременно в {', '.join(sorted(rs))}")
    return errors, warnings, subjects


def check_zameny(groups, subjects):
    errors, warnings = [], []
    vocab = {w for s in subjects for w in words(s)}
    anchor = next(iter(groups.values()))["week_anchor"]
    a_date, a_week = dt.date.fromisoformat(anchor["date"]), anchor["week"]
    for p in sorted((DATA / "zameny").glob("????-??-??.json")):
        z = json.loads(p.read_text(encoding="utf-8"))
        d = z["date"]
        # номер недели в заголовке распоряжения («Вторник, 2-я неделя») должен совпасть с расчётным
        m = re.search(r"([12])\s*-?\s*я\s+недел", z.get("title") or "", re.I)
        if m:
            weeks = (dt.date.fromisoformat(d) - a_date).days // 7
            calc = a_week if weeks % 2 == 0 else 3 - a_week
            if int(m.group(1)) != calc:
                warnings.append(f"замены {d}: в распоряжении {m.group(1)}-я неделя, а по расчёту {calc}-я — проверить week_anchor")
        if not z.get("po_raspisaniyu") and not z.get("ocr_ok"):
            warnings.append(f"замены {d}: таблицу распознать не удалось")
        for g, rows in (z.get("all_changes") or {}).items():
            if g != "?" and g not in groups:
                warnings.append(f"замены {d}: неизвестная группа «{g}»")
            if g == "?":
                warnings.append(f"замены {d}: {len(rows)} строк без распознанной группы")
            for r in rows:
                if r.get("room") and not ROOM_RE.match(r["room"]) and r["room"] not in NAMED_ROOMS:
                    warnings.append(f"замены {d} {g}: странный кабинет «{r['room']}»")
                if r.get("uncertain"):
                    warnings.append(f"замены {d} {g}: распознано неуверенно — «{r['subject']}»")
                if r["subject"] != "Отменить" and r["subject"] != "Разговоры о важном":
                    bad = [w for w in words(r["subject"]) if len(w) >= 6 and w not in vocab]
                    if bad:
                        warnings.append(f"замены {d} {g}: незнакомые слова {bad} в «{r['subject']}»")
    return errors, warnings


def main():
    groups = load_groups()
    staff_file = DATA / "teachers.json"
    staff = set(json.loads(staff_file.read_text(encoding="utf-8"))["by_short"]) if staff_file.exists() else set()
    errors, warnings, subjects = check_schedules(groups, staff)
    for a, b in similar_names(subjects):
        warnings.append(f"похожие названия предметов: «{a}» / «{b}»")
    for a, b in typo_words(subjects):
        errors.append(f"опечатка-перестановка в названиях предметов: «{a}» / «{b}»")
    ze, zw = check_zameny(groups, subjects)
    errors += ze
    warnings += zw
    for e in errors:
        print("ОШИБКА:", e)
    for w in warnings:
        print("проверить:", w)
    print(f"групп: {len(groups)}, предметов: {len(subjects)}; ошибок: {len(errors)}, предупреждений: {len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
