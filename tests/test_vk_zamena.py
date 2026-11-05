"""Проверка разбора замены из беседы ВК: дата с картинки и решение «публиковать или задача».

Картинки распознавать здесь не нужно — проверяем только разбор текста и решение.
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import vk_zamena  # noqa: E402

TODAY = dt.date(2026, 11, 5)
# как в настоящем распоряжении: дата распоряжения сверху, дата замены — в тексте «на ... года»
RASPORYAZHENIE = ("05 ноября 2026 года № 65 Внести следующие изменения в расписание учебных занятий "
                  "очного отделения на 06.11.2026 года:")


def test_date_by_numbers():
    assert vk_zamena.date_from_text(RASPORYAZHENIE, TODAY) == "2026-11-06"


def test_date_by_words():
    text = "от 5 ноября 2026 года Внести изменения в расписание на 7 ноября 2026 года"
    assert vk_zamena.date_from_text(text, TODAY) == "2026-11-07"


def test_date_after_na_wins():
    # дата распоряжения (05.11) и дата замены (07 ноября) — нужна та, что после «на»
    text = "Распоряжение от 05.11.2026 Внести изменения в расписание на 07 ноября 2026 года"
    assert vk_zamena.date_from_text(text, TODAY) == "2026-11-07"


def test_only_date_after_na():
    # без «на» дата замены не ищется: в распоряжении остаётся дата распоряжения — берём последнюю
    text = "Распоряжение от 05.11.2026"
    assert vk_zamena.date_from_text(text, TODAY) == "2026-11-05"


def test_slovo_ne_na():
    # «например» — не «на»
    text = "например, изменения в расписании на 07.11.2026 года"
    assert vk_zamena.date_from_text(text, TODAY) == "2026-11-07"


def test_no_date():
    assert vk_zamena.date_from_text("Внести изменения в расписание учебных занятий", TODAY) is None


def test_date_too_far():
    # дата из другой эпохи — не наша замена
    assert vk_zamena.date_from_text("на 01.01.2020 года", TODAY) is None


def test_date_too_far_ahead():
    assert vk_zamena.date_from_text("на 01.06.2027 года", TODAY) is None


def _meta(**over):
    meta = {"ocr_ok": True, "ocr_uncertain": False, "ocr_group_doubt": False,
            "week_doubt": False, "groups_in_order": ["21-С"]}
    meta.update(over)
    return meta


def test_clean_publishes():
    assert vk_zamena.is_clean(_meta())


def test_uncertain_does_not_publish():
    for key in ("ocr_uncertain", "ocr_group_doubt", "week_doubt"):
        meta = _meta(**{key: True})
        assert not vk_zamena.is_clean(meta)
        assert vk_zamena.why(meta)


def test_without_groups_does_not_publish():
    meta = _meta(groups_in_order=[])
    assert not vk_zamena.is_clean(meta)
    assert vk_zamena.why(meta)


def test_broken_table_does_not_publish():
    meta = _meta(ocr_ok=False)
    assert not vk_zamena.is_clean(meta)
    assert vk_zamena.why(meta)


def test_incoming_groups():
    # страницы одного распоряжения — рядом: 123_1.png и 123_2.png разбираются вместе
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for name in ("123_2.png", "123_1.png", "456_1.jpg", "заметка.txt"):
            (d / name).write_bytes(b"x")
        groups = vk_zamena.incoming_groups(d)
    assert sorted(groups) == ["123", "456"]
    assert [p.name for p in groups["123"]] == ["123_1.png", "123_2.png"]
    assert [p.name for p in groups["456"]] == ["456_1.jpg"]
