"""Календарный учебный график из PDF и новости техникума (на сохранённых копиях).

    python -m pytest tests -q
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXD = Path(__file__).parent / "fixtures" / "data"  # замороженный снимок данных, а не живые data/
FIX = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(ROOT / "tools"))
import extract_calendar as EC  # noqa: E402
import news  # noqa: E402


@pytest.fixture(scope="module")
def cal():
    return EC.extract(FIX / "kug_2026-2027.pdf")


def test_holidays(cal):
    assert [(h["date"], h["name"]) for h in cal["holidays"]] == [
        ("2026-11-04", "День народного единства"), ("2027-02-23", "День защитника Отечества"),
        ("2027-03-08", "Международный женский день"), ("2027-05-01", "Праздник Весны и Труда"),
        ("2027-05-10", "День Победы (перенос с 9 мая)"), ("2027-06-12", "День России")]


def test_all_19_groups(cal):
    assert len(cal["groups"]) == 19


def test_11A_matches_site_calendar(cal):
    """data/calendar.json, по которому работает сайт, совпадает с извлечённым из PDF."""
    site = json.loads((FIXD / "calendar.json").read_text(encoding="utf-8"))
    assert site["holidays"] == cal["holidays"]
    assert site["groups"]["11-А"] == cal["groups"]["11-А"]
    s = [p for p in cal["groups"]["11-А"]["periods"] if p["type"] == "sessiya"][0]
    assert (s["from"], s["to"]) == ("2027-06-24", "2027-06-28")
    assert s["exams"] == ["Русский язык (диктант)", "Математика (письм)", "Физика (устно)", "История (устно)"]


def test_first_course_groups_identical(cal):
    first = [g for g in cal["groups"] if g.startswith("11-")]
    assert all(cal["groups"][g]["periods"] == cal["groups"]["11-А"]["periods"] for g in first)


def test_season_names_and_practice(cal):
    p41 = cal["groups"]["41-П"]["periods"]
    assert p41[0]["type"] == "praktika" and p41[0]["from"] == "2026-09-01"
    assert ("Осенние каникулы", "2026-10-13", "2026-10-19") in [(p["name"], p["from"], p["to"]) for p in p41]
    assert all(p["no_classes"] for p in p41 if p["type"] in ("praktika", "kanikuly"))


def test_news_parse():
    items = news.parse((FIX / "novosti_2026-10-27.html").read_text(encoding="utf-8"))
    assert len(items) == 10
    assert items[0] == {"title": "Обучение по Эксплуатации беспилотных авиационных систем", "date": "14 октября 2026",
                        "url": "https://utgt-pgups.ru/512-obuchenie-po-ekspluatatsii-bespilotnykh-aviatsionnykh-sistem.html"}


def test_specialties(cal):
    spec = {g: (v["specialty"]["code"], v["specialty"]["name"]) for g, v in cal["groups"].items()}
    assert spec["11-А"] == ("23.02.09", "Автоматика и телемеханика на транспорте (железнодорожном транспорте)")
    assert spec["31-А"][0] == "27.02.03"   # старшие курсы учатся по старому коду
    assert spec["11-С"] == ("11.02.06", "Техническая эксплуатация транспортного радиоэлектронного оборудования (по видам транспорта)")
    assert spec["11-В"][1].endswith("(Вагоны)") and spec["11-Л"][1].endswith("(Локомотивы)")
    assert all(not re.search(r"\b[IV]+\b|[IV]{2,}", name) for _, name in spec.values())  # номера курсов не прилипли


def test_practice_names_and_courseworks(cal):
    names = [p["name"] for p in cal["groups"]["31-А"]["periods"] if p["type"] == "praktika"]
    assert "Учебная практика: Монтаж устройств СЦБ и ЖАТ" in names
    assert "Производственная практика (по профилю специальности)" in names
    assert cal["groups"]["11-А"]["courseworks"] == {}
    assert cal["groups"]["41-А"]["courseworks"]["2"][0].startswith("КП: МДК.01.01")
