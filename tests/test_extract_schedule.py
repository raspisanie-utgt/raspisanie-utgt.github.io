"""Извлечение расписания всех групп из PDF (заготовка для сайта со всеми группами).

    python -m pytest tests -q
"""
import json
import sys
from pathlib import Path

import pdfplumber
import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXD = Path(__file__).parent / "fixtures" / "data"  # замороженный снимок данных, а не живые data/
sys.path.insert(0, str(ROOT / "tools"))
import extract_schedule as E  # noqa: E402

PDF = Path(__file__).parent / "fixtures" / "raspisanie_2026-2027_s1.pdf"


@pytest.fixture(scope="module")
def sheet():
    return E.Sheet(pdfplumber.open(PDF).pages[0])


def test_all_groups_found(sheet):
    assert list(sheet.groups) == ["11-П", "11-Д", "11-А", "11-С", "11-В", "11-Л", "21-П", "21-Д", "21-А", "21-С",
                                  "21-Л", "31-П", "31-Д", "31-А", "31-С", "41-П", "41-Д", "41-А", "41-С"]


def test_11A_matches_hand_checked_schedule(sheet):
    days, warnings = sheet.group("11-А")
    assert warnings == []
    assert days == json.loads((FIXD / "groups" / "11a.json").read_text(encoding="utf-8"))["days"]


def test_21P_matches_pdf_by_eye(sheet):
    """21-П сверена с картинкой PDF вручную — много пар по неделям."""
    days, _ = sheet.group("21-П")
    brief = {d: [(e["lessons"][0], e.get("week"), e["subject"], e["room"]) for e in v] for d, v in days.items()}
    assert brief["1"][-1] == (7, 2, "Прикладная математика", "1-8")      # пн, 4-я пара только 2-я неделя
    assert brief["5"][1:3] == [(5, 1, "Электротехника и электроника", "1-14"), (5, 2, "Инженерная графика", "1-25")]
    assert brief["6"] == [(1, 1, "Геодезия", "2-2"), (3, None, "Геодезия", "2-2"),
                          (5, 2, "Метрология, стандартизация и сертификация", "1-14"), (7, 2, "История России", "2-10")]


def test_no_warnings_and_teachers_everywhere(sheet):
    for g in sheet.groups:
        days, warnings = sheet.group(g)
        assert warnings == [], g
        for v in days.values():
            for e in v:
                assert e["subject"] and (e["teacher"] or e["lessons"] == [0]), (g, e)
                assert not E.TAIL_NAME_RE.search(e["subject"]), (g, e["subject"])  # фамилия не прилипла к предмету


def test_white_fill_is_not_a_week_split(sheet):
    """Край белой заливки ячейки раньше принимался за черту «1-я / 2-я неделя»."""
    days, _ = sheet.group("21-П")
    assert [e for e in days["2"] if e["lessons"] == [3, 4]] == [
        {"lessons": [3, 4], "subject": "Электротехника и электроника", "teacher": "Абрамова Т.Ю.", "room": "1-14"}]


def test_teacher_names_are_clean(sheet):
    """Фамилия не прилипает к предмету и не теряется при переносе инициалов на новую строку."""
    import re
    name = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s[А-ЯЁ]\.\s?[А-ЯЁ]\.?$")
    for g in sheet.groups:
        days, _ = sheet.group(g)
        for v in days.values():
            for e in v:
                for t in filter(None, e["teacher"].split(" / ")):
                    assert name.match(t), (g, t, e["subject"])
    days, _ = sheet.group("41-А")
    assert any(e["teacher"] == "Добряков Ю.В." and e["subject"].endswith("жд автом.") for e in days["4"])


def test_subgroups_split(sheet):
    """21-С, вторник, 1 пара: подгруппы английский / немецкий — не склеиваются в одну строку."""
    days, _ = sheet.group("21-С")
    e = [x for x in days["2"] if x["lessons"] == [1, 2]][0]
    assert e == {"lessons": [1, 2], "subject": "Иностранный язык (английский) / Иностранный язык (немецкий)",
                 "teacher": "Баякчан Л.А. / Хаменева И.И.", "room": "2-15 / 1-14"}


def test_teacher_initials_typo_fixed_by_staff_list():
    from extract_schedule import teacher_fixer
    fix = teacher_fixer(["Канева Ольга Петровна", "Иванов Иван Иванович", "Иванова Анна Петровна"])
    days = {"2": [{"teacher": "Канева О.В.", "subject": "Информатика"}],
            "3": [{"teacher": "Баякчан Л.А. / Канева О.В.", "subject": "А / Б"}, {"teacher": "", "subject": "РоВ"}]}
    assert fix(days) == ["Канева О.В. -> Канева О.П.", "Баякчан Л.А. / Канева О.В. -> Баякчан Л.А. / Канева О.П."]
    assert days["2"][0]["teacher"] == "Канева О.П."


def test_popravki_rename_subject_and_fix_room():
    days = {"2": [{"lessons": [3, 4], "subject": "Иностранный язык (английский)", "teacher": "Баякчан Л.А.", "room": "1-15"}],
            "4": [{"lessons": [5, 6], "subject": "МДК.02.01 Основы технического обслуживания устройств и систем СЦБ и ЖАТ",
                   "teacher": "Туйманов Ю.Н.", "room": "1-30"}]}
    pop = json.loads((FIXD / "popravki.json").read_text(encoding="utf-8"))
    E.apply_popravki("21-Л", days, pop)
    assert days["2"][0]["room"] == "2-15" and "Баякчан" in days["2"][0]["note"]
    assert days["4"][0]["subject"] == "МДК.02.01 Основы технического обслуживания устройств систем СЦБ и ЖАТ"
    other = {"2": [{"lessons": [3, 4], "subject": "Физика", "teacher": "", "room": "1-15"}]}
    E.apply_popravki("31-Д", other, pop)
    assert other["2"][0]["room"] == "1-15"  # поправка только для своей группы

