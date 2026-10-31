"""Полные ФИО преподавателей из PDF «Педагогический состав» (сохранённая копия)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXD = Path(__file__).parent / "fixtures" / "data"  # замороженный снимок данных, а не живые data/
sys.path.insert(0, str(ROOT / "tools"))
import teachers as T  # noqa: E402

PDF = Path(__file__).parent / "fixtures" / "pedsostav_2026-09-10.pdf"


def test_full_names_from_pdf():
    full = T.full_names(PDF)
    assert len(full) == 23
    assert full[0] == "Абрамова Татьяна Юрьевна"
    assert "Черных Светлана Семёновна" in full and "Изъюрова Наталья Михайловна" in full


def test_match_short_names():
    full = T.full_names(PDF)
    assert T.match("Изъюрова Н.М.", full) == "Изъюрова Наталья Михайловна"
    assert T.match("Черных С.С.", full) == "Черных Светлана Семёновна"   # ё/е
    assert T.match("Канева О.В.", full) == "Канева Ольга Петровна"       # опечатка в отчестве в расписании
    assert T.match("Дудников В.Ю.", full) is None                        # нет в списке педсостава
    assert T.match("Ю.В.", full) is None


def test_every_11A_teacher_has_full_name():
    by_short = json.loads((FIXD / "teachers.json").read_text(encoding="utf-8"))["by_short"]
    sched = json.loads((FIXD / "groups" / "11a.json").read_text(encoding="utf-8"))
    for day in sched["days"].values():
        for e in day:
            assert not e["teacher"] or e["teacher"] in by_short, e["teacher"]
