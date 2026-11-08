"""Данные расписаний без явных ошибок: пустых предметов, накладок, странных кабинетов и имён, опечаток."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_data  # noqa: E402


def test_schedules_have_no_errors():
    groups = check_data.load_groups()
    errors, _, subjects = check_data.check_schedules(groups, set())
    assert errors == []
    assert check_data.typo_words(subjects) == []


def test_typo_detector_finds_letter_swaps():
    assert check_data.typo_words(["Безопасность жизнедеятельности", "Техническая безопансость"]) == [
        ("безопансость", "безопасность")]


def test_room_ok_two_rooms_and_auditorium():
    """Два кабинета через «/» (с пробелами и без) и «акт. зал» — нормальные значения."""
    assert check_data.room_ok("1-28 / 2-15")
    assert check_data.room_ok("1-14/2-7")
    assert check_data.room_ok("акт. зал")
    assert check_data.room_ok("2-7")
    assert not check_data.room_ok("1-28 / 2-15 / аудитория")
    assert not check_data.room_ok("1-28 / 2-15 / ???")
