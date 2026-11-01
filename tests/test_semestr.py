"""Новый семестр и новый учебный год — сами (tools/semestr.py), на сохранённых PDF и копии данных."""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import extract_schedule  # noqa: E402
import semestr  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
SCHED_PDF = FIX / "raspisanie_2026-2027_s1.pdf"
KUG_PDF = FIX / "kug_2026-2027.pdf"
CUR = "https://utgt-pgups.ru/images/Raspisanie%20ucebnyh%20zanatij%201%20semestr%202026-2027.pdf"
NEW = "https://utgt-pgups.ru/images/Raspisanie%20ucebnyh%20zanatij%202%20semestr%202026-2027.pdf"
D = dt.date.fromisoformat


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(FIX / "data" / "groups", d / "groups")
    shutil.copyfile(FIX / "data" / "calendar.json", d / "calendar.json")
    return d


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def site(monkeypatch, pdfs, files, fps=None):
    """Сайт техникума: на странице pdfs, по адресу — файл из files, «отпечаток» — fps."""
    monkeypatch.setattr(semestr.sources, "page_pdfs", lambda: pdfs)
    monkeypatch.setattr(semestr.sources, "fingerprint", lambda u: (fps or {}).get(u, {"size": "1"}))

    def download(url, folder):
        p = Path(folder) / "file.pdf"
        shutil.copyfile(files[url], p)
        return p
    monkeypatch.setattr(semestr, "download", download)


def test_first_run_only_remembers(data, monkeypatch):
    site(monkeypatch, [CUR], {})
    semestr.main(data, D("2026-11-01"))
    assert CUR in load(data / "semestr.json")["tried"]
    assert not (data / "notices.txt").exists() and not (data / "next").exists()


def test_new_semester_waits_for_break_then_switches(data, monkeypatch):
    real = extract_schedule.pdf_info
    monkeypatch.setattr(extract_schedule, "pdf_info", lambda p: {**real(p), "semester": 2})  # «PDF 2 семестра»
    site(monkeypatch, [CUR, NEW], {NEW: SCHED_PDF})
    old_anchor = load(data / "groups" / "11a.json")["week_anchor"]
    semestr.main(data, D("2026-12-01"))
    nxt = load(data / "next" / "index.json")
    # 2 семестр — со дня после зимних каникул (29.12–11.01); на сайт — в первый день каникул
    assert (nxt["semester"], nxt["valid_from"], nxt["valid_to"], nxt["switch_on"]) == (2, "2027-01-12", "2027-08-31", "2026-12-29")
    assert load(data / "groups" / "index.json")["semester"] == 1  # пока — старое
    assert "появится на сайте 2026-12-29" in (data / "notices.txt").read_text(encoding="utf-8")
    semestr.main(data, D("2026-12-28"))
    assert (data / "next").exists()
    # пока ждали, нумерацию недель поправили по распоряжениям — новое расписание возьмёт поправленную
    for f in (data / "groups").glob("*.json"):
        if f.name != "index.json":
            g = load(f)
            g["week_anchor"] = old_anchor = {"date": "2026-12-21", "week": 2}
            f.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    semestr.main(data, D("2026-12-29"))
    cur = load(data / "groups" / "index.json")
    assert not (data / "next").exists() and cur["semester"] == 2 and "switch_on" not in cur
    assert not any(g["verified"] for g in cur["groups"])  # не сверено человеком — сайт так и пишет
    g = load(data / "groups" / "11a.json")
    assert g["source"] == NEW and g["week_anchor"] == old_anchor and g["days"]
    # ручная правка пары прошлого PDF к новому не применяется
    assert not any("note" in e for es in load(data / "groups" / "21l.json")["days"].values() for e in es)


def test_late_schedule_goes_live_at_once(data, monkeypatch):
    real = extract_schedule.pdf_info
    monkeypatch.setattr(extract_schedule, "pdf_info", lambda p: {**real(p), "semester": 2})
    site(monkeypatch, [CUR, NEW], {NEW: SCHED_PDF})
    semestr.main(data, D("2027-01-20"))
    assert load(data / "groups" / "index.json")["semester"] == 2 and not (data / "next").exists()


def test_same_pdf_reuploaded_keeps_verified(data, monkeypatch):
    site(monkeypatch, [CUR], {CUR: SCHED_PDF}, {CUR: {"size": "1"}})
    semestr.main(data, D("2026-11-01"))  # запомнил
    site(monkeypatch, [CUR], {CUR: SCHED_PDF}, {CUR: {"size": "2"}})  # перезалили тот же файл
    semestr.main(data, D("2026-11-02"))
    assert not (data / "notices.txt").exists()
    assert all(g["verified"] for g in load(data / "groups" / "index.json")["groups"])


def test_changed_pdf_of_same_semester(data, monkeypatch):
    f = data / "groups" / "11a.json"
    g = load(f)
    g["days"]["1"] = g["days"]["1"][:1]  # «старое» расписание 11-А отличалось
    f.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    site(monkeypatch, [CUR], {CUR: SCHED_PDF}, {CUR: {"size": "1"}})
    semestr.main(data, D("2026-11-01"))
    site(monkeypatch, [CUR], {CUR: SCHED_PDF}, {CUR: {"size": "2"}})
    semestr.main(data, D("2026-11-02"))
    idx = {g["group"]: g for g in load(data / "groups" / "index.json")["groups"]}
    assert not idx["11-А"]["verified"] and idx["11-Д"]["verified"]
    assert "Изменились группы: 11-А" in (data / "notices.txt").read_text(encoding="utf-8")
    assert len(load(data / "groups" / "11a.json")["days"]["1"]) > 1


def test_old_or_broken_pdf_changes_nothing(data, monkeypatch, tmp_path):
    before = {p.name: p.read_bytes() for p in (data / "groups").glob("*.json")}
    old = NEW.replace("2026-2027", "2025-2026")
    real = extract_schedule.pdf_info
    monkeypatch.setattr(extract_schedule, "pdf_info", lambda p: {**real(p), "year": "2025/2026", "semester": 2})
    site(monkeypatch, [CUR, old], {old: SCHED_PDF})
    semestr.main(data, D("2026-11-01"))
    assert {p.name: p.read_bytes() for p in (data / "groups").glob("*.json")} == before
    # не PDF расписания вовсе
    monkeypatch.setattr(extract_schedule, "pdf_info", lambda p: None)
    site(monkeypatch, [CUR, NEW], {NEW: KUG_PDF})
    semestr.main(data, D("2026-11-01"))
    assert {p.name: p.read_bytes() for p in (data / "groups").glob("*.json")} == before
    assert "не понял" in (data / "notices.txt").read_text(encoding="utf-8")


def test_check_schedule_catches_bad_parse(tmp_path):
    out = tmp_path / "g"
    shutil.copytree(FIX / "data" / "groups", out)
    old = load(out / "index.json")
    assert semestr.check_schedule(out, old) == []
    bad = dict(old, groups=old["groups"][:5])
    (out / "index.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    assert any("групп" in p for p in semestr.check_schedule(out, old))
    g = load(out / "11a.json")
    g["days"] = {"1": g["days"]["1"]}
    (out / "11a.json").write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    assert any("11-А" in p for p in semestr.check_schedule(out, bad))


def test_check_calendar():
    cal = load(FIX / "data" / "calendar.json")
    assert semestr.check_calendar(cal, 2026) == []
    shifted = dict(cal, holidays=[dict(h, date=(D(h["date"]) + dt.timedelta(days=1)).isoformat()) for h in cal["holidays"]])
    assert semestr.check_calendar(shifted, 2026)  # дни недели поняты со сдвигом — праздники не на своих датах


def test_new_year_calendar_is_merged(data, monkeypatch, tmp_path):
    nxt = "https://utgt-pgups.ru/images/Svodnyj%20KUG%20ocnoe%20otdelenie%202027-2028%20ucebnyj%20god.pdf"
    cal = load(data / "calendar.json")
    new = json.loads(json.dumps(cal).replace("2027-", "2028-").replace("2026-", "2027-"))  # «график на 2027/28»
    new["title"] = new["title"].replace("2026-2027", "2027-2028")
    monkeypatch.setattr(semestr.extract_calendar, "pdf_year", lambda p: 2027)
    monkeypatch.setattr(semestr.extract_calendar, "extract", lambda p: new)
    monkeypatch.setattr(semestr, "check_calendar", lambda c, y: [])
    site(monkeypatch, [cal["source"], nxt], {nxt: KUG_PDF})
    semestr.main(data, D("2027-08-25"))
    merged = load(data / "calendar.json")
    dates = [h["date"] for h in merged["holidays"]]
    assert "2026-11-04" in dates and "2027-11-04" in dates and dates == sorted(dates)
    per = merged["groups"]["11-А"]["periods"]
    assert per[0]["from"] == "2026-12-29" and any(p["from"] == "2027-12-29" for p in per)
    assert "2027/2028" in (data / "notices.txt").read_text(encoding="utf-8")
    # график 2027/28 перезалили — прошлый год (до 1 сентября) остаётся
    new["holidays"].append({"date": "2028-03-09", "name": "Праздничный день"})
    other = tmp_path / "kug2.pdf"
    other.write_bytes(KUG_PDF.read_bytes() + b"\n%")  # другой файл (тот же по содержимому сайт пропускает)
    site(monkeypatch, [nxt], {nxt: other}, {nxt: {"size": "2"}})
    semestr.main(data, D("2027-08-26"))
    again = load(data / "calendar.json")
    assert "2026-11-04" in [h["date"] for h in again["holidays"]] and "2028-03-09" in [h["date"] for h in again["holidays"]]
    assert again["groups"]["11-А"]["periods"][0]["from"] == "2026-12-29"


def test_switch_on():
    cal = load(FIX / "data" / "calendar.json")
    assert semestr.switch_on("2027-01-12", cal, D("2026-12-01")) == D("2026-12-29")
    assert semestr.switch_on("2027-01-12", cal, D("2027-01-05")) == D("2027-01-06")  # уже каникулы — с завтра
    assert semestr.switch_on("2027-01-12", cal, D("2027-01-20")) == D("2027-01-20")
    # перед 1 сентября — летние каникулы почти у всех: за 3 недели
    assert semestr.switch_on("2027-09-01", cal, D("2027-06-01")) == D("2027-08-11")
    assert semestr.semester_dates({"semester": 1, "year": "2027/2028"}, cal, {}) == ("2027-09-01", "2028-01-11", True)


def test_broken_pdf_note_once_and_no_redownload(data, monkeypatch, tmp_path):
    """Вёрстка PDF другая — заметка человеку один раз; тот же файл больше не качаем каждый час."""
    real = extract_schedule.pdf_info
    monkeypatch.setattr(extract_schedule, "pdf_info", lambda p: {**real(p), "semester": 2})
    monkeypatch.setattr(extract_schedule, "extract_all", lambda *a, **k: (_ for _ in ()).throw(AssertionError("нашлось дней: 1")))
    site(monkeypatch, [CUR, NEW], {NEW: SCHED_PDF})
    calls = []
    real_dl = semestr.download
    monkeypatch.setattr(semestr, "download", lambda u, f: calls.append(u) or real_dl(u, f))
    for day in ("2026-12-01", "2026-12-01", "2026-12-02"):
        semestr.main(data, D(day))
    text = (data / "notices.txt").read_text(encoding="utf-8")
    assert text.count("разобрать не вышло") == 1 and "нашлось дней" in text
    assert calls == [NEW] and not (data / "next").exists()


def test_fix_of_current_pdf_while_next_waits(data, monkeypatch):
    real = extract_schedule.pdf_info
    monkeypatch.setattr(extract_schedule, "pdf_info", lambda p: {**real(p), "semester": 2})
    site(monkeypatch, [CUR, NEW], {NEW: SCHED_PDF}, {CUR: {"size": "1"}})
    semestr.main(data, D("2026-12-01"))
    assert (data / "next").exists()
    f = data / "groups" / "11a.json"
    g = load(f)
    g["days"]["1"] = g["days"]["1"][:1]
    f.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(extract_schedule, "pdf_info", real)  # перезалили PDF 1 семестра
    site(monkeypatch, [CUR, NEW], {CUR: SCHED_PDF, NEW: SCHED_PDF}, {CUR: {"size": "2"}})
    semestr.main(data, D("2026-12-02"))
    assert len(load(f)["days"]["1"]) > 1 and load(data / "next" / "index.json")["semester"] == 2


def test_switch_on_with_next_year_calendar_merged():
    cal = load(FIX / "data" / "calendar.json")
    nxt = json.loads(json.dumps(cal).replace("2027-", "2028-").replace("2026-", "2027-"))
    merged = semestr.merge_calendars(cal, nxt, 2027)
    assert semestr.switch_on("2027-09-01", merged, D("2027-06-01")) == D("2027-08-11")
