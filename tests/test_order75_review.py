import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import scraper
from tools import vk_ai, vk_zamena


@pytest.mark.parametrize("lessons", [[3, 8], [3, 6], [7, 10]])
def test_order75_model_range_requires_every_lesson(lessons):
    row = {"group": "31-А", "lessons": lessons, "time": "", "subject": "Учебная практика", "room": "1-10"}
    with pytest.raises(ValueError, match="диапазон уроков указан не полностью"):
        vk_ai._row(row, {"31-А"})
    row["lessons"] = list(range(lessons[0], lessons[-1] + 1))
    assert vk_ai._row(row, {"31-А"})[1] == tuple(row["lessons"])


def test_order75_archived_photo_matches_all_verified_rows_without_publishing(tmp_path, monkeypatch):
    exe = shutil.which("tesseract")
    if not exe or not {b"rus", b"eng"} <= set(subprocess.check_output([exe, "--list-langs"]).splitlines()):
        pytest.skip("Russian and English Tesseract data required")
    data = Path(__file__).resolve().parents[1] / "data"
    photo = next((data / "vk-review").glob("*/82_1.png"))
    monkeypatch.setattr(scraper, "DATA", data)
    monkeypatch.delenv("OPENROUTER_MODE", raising=False)
    readings = []
    read_table = scraper.ocr_table
    def capture(*args, **kwargs):
        table = read_table(*args, **kwargs)
        readings.append(table)
        return table
    monkeypatch.setattr(scraper, 'ocr_table', capture)
    result = vk_zamena.publish([photo], tmp_path, dt.date(2026, 11, 17), dry=True)
    assert result["date"] == "2026-11-18"
    assert result["status"] == "ok" and result["dry"]
    # Сверено со всеми 15 строками изображения №75, а не с прежним статусом OCR.
    expected = json.loads((Path(__file__).parent / 'fixtures/order75-expected.json').read_text(encoding='utf-8'))
    assert len(readings) == 2
    for table in readings:
        assert table['ok'] and len(table['rows']) == 15
        assert scraper.all_group_changes([table]) == expected
    assert not list(tmp_path.iterdir())


def test_order76_unconfirmed_language_pair_still_requires_review(tmp_path, monkeypatch):
    exe = shutil.which("tesseract")
    if not exe or not {b"rus", b"eng"} <= set(subprocess.check_output([exe, "--list-langs"]).splitlines()):
        pytest.skip("Russian and English Tesseract data required")
    data = Path(__file__).resolve().parents[1] / "data"
    photo = next((data / "vk-review").glob("*/89_1.png"))
    monkeypatch.setattr(scraper, 'DATA', data)
    monkeypatch.setattr(vk_zamena, 'add_ai_suggestion', lambda *args: None)
    result = vk_zamena.publish([photo], tmp_path, dt.date(2026, 11, 20), dry=True)
    assert result['date'] == '2026-11-19'
    assert result['status'] == 'uncertain'
    assert len(result['ocr_rows'][0]) == 17
    assert '11-В' in result['reason'] and 'название дисциплины не подтверждено' in result['reason']
    assert not list(tmp_path.iterdir())


def test_review_details_distinguishes_ocr_and_timetable_checks():
    row = {"group": "11-А", "lessons": [9, 10], "subject": scraper.CANCEL,
           "uncertain": True, "review": ["OCR: чтения номеров уроков расходятся"]}
    tables = [{"ok": True, "rows": [row]}]
    scraper.check_with_schedule(tables, "2026-11-18", schedules={"11-А": {"days": {}}}, past={})
    summary = vk_zamena.review_details(tables)
    assert "Лист 1, строка 1 (11-А): OCR:" in summary
    assert "Расписание: ни один отменяемый урок не найден" in summary


def test_practice_vocabulary_uses_calendar():
    vocab = scraper.subject_vocab()
    assert "Учебная практика" in vocab
    assert "Учебная практика: Монтаж устройств СЦБ и ЖАТ" in vocab
    assert scraper.snap_subject("Учебная практика", vocab) == ("Учебная практика", True)
    assert not scraper.snap_subject("Учебная практика: выдуманная специальность", vocab)[1]
    assert not scraper.snap_subject("Несуществующая дисциплина XYZ", vocab)[1]


def test_order_number_conflict_is_reported(monkeypatch):
    monkeypatch.setattr(vk_zamena, "ocr_text", lambda path, psm: "РАСПОРЯЖЕНИЕ № " + ("75" if psm == 6 else "175"))
    report = vk_zamena.order_number_evidence(["photo.png"])
    assert "75" in report and "175" in report and "расходится" in report


def test_ocr_text_decodes_utf8(monkeypatch):
    from types import SimpleNamespace
    def run(*args, **kwargs):
        assert kwargs["encoding"] == "utf-8"
        return SimpleNamespace(stdout="Учебная практика")
    monkeypatch.setattr(subprocess, "run", run)
    assert vk_zamena.ocr_text("photo.png") == "Учебная практика"


def test_practice_is_not_invented_without_calendar(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "DATA", tmp_path)
    assert "Учебная практика" not in scraper.subject_vocab()


def test_subject_retry_requires_two_exact_readings(monkeypatch):
    from PIL import Image
    image = Image.new("L", (100, 30), 255)
    values = iter(["Физика", "Химия"])
    monkeypatch.setattr(scraper, "read_binary_cell", lambda *args: next(values))
    assert scraper._reread_legacy_subject(image, (0, 0, 100, 30), ["Физика", "Химия"]) is None
    monkeypatch.setattr(scraper, "read_binary_cell", lambda *args: "Физика")
    assert scraper._reread_legacy_subject(image, (0, 0, 100, 30), ["Физика"]) == "Физика"
    assert scraper._reread_legacy_subject(image, (0, 0, 100, 30), ["Химия"]) is None
