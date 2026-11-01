import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sources  # noqa: E402


def state(fp, pdfs):
    return {"files": {"звонки": {"url": "u/zvonki.pdf", "fp": fp}}, "page_pdfs": pdfs}


def test_changes():
    a = state({"size": "1", "etag": "x"}, ["u/raspisanie 1 semestr.pdf"])
    assert sources.changes({}, a) == []  # первая проверка — только запомнить
    assert sources.changes(a, a) == []
    b = state({"size": "2", "etag": "y"}, ["u/raspisanie 1 semestr.pdf", "u/raspisanie 2 semestr.pdf", "u/zvonki 2.pdf"])
    found = sources.changes(a, b)
    # новое расписание разбирает tools/semestr.py — о нём здесь задачи нет
    assert len(found) == 2 and "звонки" in found[0] and "zvonki 2" in found[1]
