"""Данные расписаний без явных ошибок: пустых предметов, накладок, странных кабинетов и имён, опечаток."""
import sys
import json
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


def test_practice_audit_uses_calendar_without_hiding_unknown_words(tmp_path, monkeypatch):
    monkeypatch.setattr(check_data, 'DATA', tmp_path)
    (tmp_path / 'zameny').mkdir()
    (tmp_path / 'calendar.json').write_text(json.dumps({'groups': {'31-А': {'periods': [
        {'type': 'praktika', 'name': 'Учебная практика: Монтаж устройств СЦБ и ЖАТ'}]}}}), encoding='utf-8')
    (tmp_path / 'zameny/2026-11-19.json').write_text(json.dumps({'date': '2026-11-19', 'ocr_ok': True,
        'all_changes': {'31-А': [
            {'subject': 'Учебная практика', 'room': '1-10'},
            {'subject': 'Учебная практика: выдуманная специальность', 'room': '1-10'}]}}), encoding='utf-8')
    _, warnings = check_data.check_zameny({'31-А': {'week_anchor': {'date': '2026-11-09', 'week': 2}}}, {'Математика'})
    unknown = [value for value in warnings if 'незнакомые слова' in value]
    assert len(unknown) == 1 and 'выдуманная' in unknown[0]
