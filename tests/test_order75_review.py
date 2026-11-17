import datetime as dt
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


def test_order75_archived_photo_reports_uncertainties_without_publishing(tmp_path, monkeypatch):
    exe = shutil.which("tesseract")
    if not exe or not {"rus", "eng"} <= set(subprocess.check_output([exe, "--list-langs"], text=True).splitlines()):
        pytest.skip("Russian and English Tesseract data required")
    data = Path(__file__).resolve().parents[1] / "data"
    photo = next((data / "vk-review").glob("*/82_1.png"))
    monkeypatch.setattr(scraper, "DATA", data)
    monkeypatch.delenv("OPENROUTER_MODE", raising=False)
    result = vk_zamena.publish([photo], tmp_path, dt.date(2026, 11, 17), dry=True)
    assert result["date"] == "2026-11-18"
    assert result["status"] == "uncertain"
    assert len(result["ocr_rows"][0]) == 15
    assert "Распознано строк: 15." in result["reason"]
    assert "строка 10 (31-А)" in result["reason"]
    assert "строка 11 (31-С)" in result["reason"]
    assert not list(tmp_path.iterdir())


def test_review_details_distinguishes_ocr_and_timetable_checks():
    row = {"group": "11-А", "lessons": [9, 10], "subject": scraper.CANCEL,
           "uncertain": True, "review": ["OCR: чтения номеров уроков расходятся"]}
    tables = [{"ok": True, "rows": [row]}]
    scraper.check_with_schedule(tables, "2026-11-18", schedules={"11-А": {"days": {}}}, past={})
    summary = vk_zamena.review_details(tables)
    assert "Лист 1, строка 1 (11-А): OCR:" in summary
    assert "Расписание: ни один отменяемый урок не найден" in summary
