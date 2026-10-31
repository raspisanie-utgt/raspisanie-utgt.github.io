"""Тесты на сохранённых с сайта страницах и картинках замен (октябрь 2026).

    python -m pytest tests -q
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

import scraper

FIX = Path(__file__).parent / "fixtures"
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="нет tesseract")


def test_parse_page_finds_ochnoe_block():
    blocks = scraper.parse_page((FIX / "zamena_page_2026-10-26.html").read_text(encoding="utf-8"))
    assert [(b["date"], b["section"]) for b in blocks] == [("2026-10-27", "ochnoe"), ("2026-10-27", "zaochnoe")]
    assert blocks[0]["images"] == ["https://utgt-pgups.ru/images/27.10.2026.png"]
    assert blocks[1]["images"] == ["https://utgt-pgups.ru/images/27.10_26Z.png"]


@pytest.mark.parametrize("text,expected", [
    ("11-А", ("11-А", True)), ("2]1-А", ("21-А", True)), ("11-7", ("11-7", False)),  # цифру вместо буквы не угадываем
    ("21-С©", ("21-С", True)), ("11", (None, False)), ("и", (None, True)), ("", (None, True)),
])
def test_normalize_group(text, expected):
    assert scraper.normalize_group(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("5-6", ([5, 6], None)), ("8-30", ([0], "08:30")), ("14-50", ([], "14:50")),
    ("3—", ([3, 4], None)), ("5-10", ([5, 6, 7, 8, 9, 10], None)),
    # дефис потерялся при чтении одними цифрами
    ("34", ([3, 4], None)), ("78", ([7, 8], None)), ("910", ([9, 10], None)), ("830", ([0], "08:30")),
    ("1450", ([], "14:50")), ("10", ([10], None)), ("4", ([4], None)),
])
def test_parse_lessons(text, expected):
    assert scraper.parse_lessons(text) == expected


# Что на картинках на самом деле (проверено глазами)
EXPECTED_11A = {
    "27.10.2026.png": [],
    "26.10.2026.png": [([0], "Разговоры о важном", "1-25")],
    "24.10.2026.png": [([1, 2], "Математика", "1-8"), ([5, 6], "Химия", "2-7"), ([7, 8], "Биология", "2-7")],
    "23.10.2026.png": [([7, 8], "География", "2-7")],
    "19.10.2026.png": [([0], "Разговоры о важном", "1-25"), ([7, 8], "Физика", "2-5")],
}


@needs_tesseract
@pytest.mark.parametrize("name", sorted(EXPECTED_11A))
def test_ocr_finds_11A(name):
    t = scraper.ocr_table(FIX / name, scraper.subject_vocab())
    assert t["ok"]
    got = [(c["lessons"], c["subject"], c["room"]) for c in scraper.group_changes(t, "11-А")]
    assert got == EXPECTED_11A[name]
    assert not any(r["uncertain"] for r in t["rows"])


@needs_tesseract
def test_ocr_reads_all_groups_27_10():
    t = scraper.ocr_table(FIX / "27.10.2026.png", scraper.subject_vocab())
    groups = []
    for r in t["rows"]:
        if not groups or groups[-1] != r["group"]:
            groups.append(r["group"])
    assert groups == ["11-В", "11-Л", "21-Д", "21-С", "31-Д", "41-П", "41-А", "41-С"]
    assert t["title"] == "Вторник, 2-я неделя"


def test_snap_room_drops_table_line_read_as_one():
    known = {"1-8", "1-1", "2-18"}
    assert scraper.snap_room("1-81", known) == "1-8"   # «1-8|» — черта таблицы прочитана как «1»
    assert scraper.snap_room("2-18", known) == "2-18"  # настоящий кабинет не трогаем
    assert scraper.snap_room("1-1", known) == "1-1"
    assert scraper.snap_room("3-77", known) == "3-77"  # незнакомый и без подходящей замены — как есть
    assert scraper.snap_room("2-1Е", known | {"2-1"}) == "2-1Е"  # буква в конце — не черта таблицы


@needs_tesseract
def test_ocr_room_next_to_table_line_29_10():
    t = scraper.ocr_table(FIX / "29.10.2026.png", scraper.subject_vocab())
    rows = [r for r in t["rows"] if r["group"] == "41-С" and r["lessons"] == [9, 10]]
    assert rows and rows[0]["room"] == "1-8"


@needs_tesseract
def test_process_block_writes_json_and_skips_unchanged(tmp_path):
    png = (FIX / "24.10.2026.png").read_bytes()

    class Resp:
        content = png
        def raise_for_status(self):
            pass

    class Session:
        calls = 0
        def get(self, url, **kw):
            Session.calls += 1
            return Resp()

    block = {"date": "2026-10-24", "section": "ochnoe", "images": ["https://utgt-pgups.ru/images/24.10.2026.png"]}
    logs = []
    assert scraper.process_block(block, Session(), scraper.subject_vocab(), tmp_path, logs.append)
    meta = json.loads((tmp_path / "2026-10-24.json").read_text(encoding="utf-8"))
    assert meta["ocr_ok"] and len(meta["all_changes"]["11-А"]) == 3
    assert (tmp_path / "2026-10-24-1.png").read_bytes() == png
    # та же картинка — повторно не распознаём и файл не трогаем
    assert not scraper.process_block(block, Session(), scraper.subject_vocab(), tmp_path, logs.append)
    import datetime as dt
    scraper.write_index(tmp_path, today=dt.date(2026, 10, 26))
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["days"] == ["2026-10-24"]
    scraper.write_index(tmp_path, today=dt.date(2026, 12, 1))  # старше 21 дня — удаляется
    assert not (tmp_path / "2026-10-24.json").exists()


def test_parse_page_po_raspisaniyu():
    html = """<div class="com-content-article__body">
    <p><strong>Изменение в расписании занятий</strong></p><p><strong>на 28 октября 2026 года</strong></p>
    <p>очное отделение</p><p>по расписанию</p>
    <p><strong>на 28 октября 2026 года</strong></p><p>заочное отделение</p><p><img src="/images/28.10_26Z.png"></p>
    </div>"""
    blocks = scraper.parse_page(html)
    assert blocks == [
        {"date": "2026-10-28", "section": "ochnoe", "images": []},
        {"date": "2026-10-28", "section": "zaochnoe", "images": ["https://utgt-pgups.ru/images/28.10_26Z.png"]},
    ]


def test_process_block_po_raspisaniyu(tmp_path):
    block = {"date": "2026-10-28", "section": "ochnoe", "images": []}
    assert scraper.process_block(block, None, scraper.subject_vocab(), tmp_path, lambda *_: None)
    meta = json.loads((tmp_path / "2026-10-28.json").read_text(encoding="utf-8"))
    assert meta["po_raspisaniyu"] and meta["ocr_ok"] and meta["all_changes"] == {}


@needs_tesseract
def test_all_group_changes_27_10():
    t = scraper.ocr_table(FIX / "27.10.2026.png", scraper.subject_vocab())
    allc = scraper.all_group_changes([t])
    assert {g: len(v) for g, v in allc.items()} == {
        "11-В": 1, "11-Л": 1, "21-Д": 1, "21-С": 1, "31-Д": 1, "41-П": 2, "41-А": 1, "41-С": 4}
    assert [c["subject"] for c in allc["41-С"]][-1] == "Отменить"


@needs_tesseract
def test_all_groups_26_10_room_and_dangling_dash():
    """26.10: кабинет «2-]2» -> «2-12», урок «3-—» -> 3-4 (сверено с картинкой по всем группам)."""
    t = scraper.ocr_table(FIX / "26.10.2026.png", scraper.subject_vocab())
    allc = scraper.all_group_changes([t])
    assert allc["11-П"][0]["room"] == "2-12"
    assert [c["lessons"] for c in allc["31-А"]] == [[0], [3, 4], [], [5, 6]]
    assert allc["31-А"][2]["time"] == "12:40"
    assert {g: len(v) for g, v in allc.items()} == {
        "11-П": 2, "11-Д": 1, "11-А": 1, "11-С": 1, "11-В": 1, "11-Л": 2, "21-П": 1, "21-Д": 1, "21-А": 1,
        "21-С": 1, "21-Л": 2, "31-П": 2, "31-Д": 1, "31-А": 4, "31-С": 2, "41-П": 4, "41-С": 4}


def test_fix_digits():
    assert scraper.fix_digits("2-]2") == "2-12" and scraper.fix_digits("1-З") == "1-3"


def rows_of(tables, date):
    scraper.check_with_schedule(tables, date, tables[0].get("title", ""))
    return [(r["group"], r["lessons"], r["subject"][:22], r["room"], r["uncertain"]) for t in tables for r in t["rows"]]


@needs_tesseract
def test_ocr_whole_order_small_image_31_10():
    """Мелкая картинка (621 точка): каждую ячейку читаем несколькими способами и голосуем —
    раньше «11-П» читалось как «11-И», «21-П 7-8» как «21-Д 1-8», «2-7» как «2-1»."""
    t = scraper.ocr_table(FIX / "31.10.2026.png", scraper.subject_vocab())
    assert t["ok"] and "Суббота" in t["title"]
    C, B, M = "Отменить", "Биология", "МДК.03.01 Технологии п"
    assert rows_of([t], "2026-10-31") == [
        ("11-П", [1, 2], C, "", False), ("11-Д", [5, 6], C, "", False), ("11-Л", [7, 8], B, "2-7", False),
        ("21-П", [7, 8], C, "", False), ("21-С", [3, 4, 5, 6], C, "", False), ("41-А", [1, 2], C, "", False),
        ("41-С", [1, 2, 3, 4], C, "", False), ("41-С", [5, 6, 7, 8], M, "1-30", False)]


@needs_tesseract
def test_ocr_small_image_02_11():
    """Мелкая картинка на 29 строк: «8-30» (раньше 8-50), «7-8» (раньше 1-8), П/Д в группах, «Акт. зал»,
    кабинет 1-28 (прочитался то как 1-25, то как 1-28 — решают прошлые распоряжения 21-Д)."""
    t = scraper.ocr_table(FIX / "02.11.2026.png", scraper.subject_vocab())
    got = rows_of([t], "2026-11-02")
    assert [(g, l, r) for g, l, _, r, _ in got] == [
        ("11-П", [0], ""), ("11-П", [5, 6], ""), ("11-Д", [0], ""), ("11-Д", [7, 8], "1-30"), ("11-А", [0], "1-25"),
        ("11-С", [0], "Акт. зал"), ("11-С", [7, 8], "2-5"), ("11-В", [0], "1-9"), ("11-Л", [0], "1-3"), ("11-Л", [7, 8], "2-7"),
        ("21-П", [0], "Акт. зал"), ("21-Д", [0], "1-28"), ("21-А", [0], "1-10"), ("21-С", [0], "1-14"), ("21-Л", [0], "1-32"),
        ("31-П", [0], "2-7"), ("31-П", [1, 2], "1-9"), ("31-П", [5, 6], ""), ("31-Д", [0], "1-31"),
        ("31-А", [0], ""), ("31-А", [1, 2], ""), ("31-А", [7, 8], "1-10"), ("31-А", [5, 6], ""),
        ("31-С", [0], "1-24"), ("31-С", [7, 8], "1-32"), ("41-П", [0], ""), ("41-П", [5, 6, 7, 8], ""),
        ("41-С", [0], ""), ("41-С", [9, 10], "2-10")]
    assert not any(u for *_, u in got)


def test_check_with_schedule():
    """Отмена уроков, которых у группы в этот день нет, — неуверенно; ничья по кабинету — по расписанию."""
    sched = {"21-П": {"days": {"6": [{"lessons": [7, 8], "week": 2, "subject": "История России", "room": "2-10"}],
                               "1": [{"lessons": [1, 2], "subject": "Геодезия", "room": "2-2"}]}}}
    row = lambda **k: {"group": "21-П", "lessons": [7, 8], "time": None, "subject": "Отменить", "room": "", "uncertain": False, **k}
    t = {"rows": [row(), row(lessons=[1, 2]), row(subject="Геодезия", room="2-1", room_alts=["2-1", "2-2"]),
                  row(subject="История России", room="1-5", room_alts=["1-5", "1-6"])]}
    scraper.check_with_schedule([t], "2026-10-31", "Суббота, 2-я неделя", schedules=sched, past={})
    assert [(r["room"], r["uncertain"]) for r in t["rows"]] == [("", False), ("", True), ("2-2", False), ("1-5", True)]
    assert all("room_alts" not in r for r in t["rows"])


def test_parse_page_merges_same_date_and_skips_bad_date():
    """«Дополнение» на ту же дату ниже на странице — один блок со всеми картинками; опечатка в дате не валит разбор."""
    html = """<div itemprop="articleBody">
      <p>Замены на 3 ноября 2026 года, очное отделение</p><img src="/images/a.png">
      <p>на 31 ноября 2026 года очное отделение</p><img src="/images/bad.png">
      <p>на 3 ноября 2026 года заочное отделение</p><img src="/images/z.png">
      <p>Дополнение на 3 ноября 2026 года очное отделение</p><img src="/images/b.png"><img src="/images/a.png">
    </div>"""
    blocks = scraper.parse_page(html)
    assert [(b["date"], b["section"], [i.rsplit("/", 1)[1] for i in b["images"]]) for b in blocks] == [
        ("2026-11-03", "ochnoe", ["a.png", "b.png"]), ("2026-11-03", "zaochnoe", ["z.png"])]


def test_one_broken_day_does_not_stop_others(monkeypatch, capsys):
    """Ошибка в одном дне (битая картинка) — остальные дни разбираются, индекс пишется всегда, а сбой виден."""
    html = """<div itemprop="articleBody"><p>на 3 ноября 2026 года очное</p><img src="/x/1.png">
      <p>на 4 ноября 2026 года очное</p><img src="/x/2.png"></div>"""
    done, index = [], []
    def fake(block, *a, **k):
        if block["date"] == "2026-11-03":
            raise RuntimeError("404")
        done.append(block["date"])
    monkeypatch.setattr(scraper, "process_block", fake)
    monkeypatch.setattr(scraper, "write_index", lambda *a, **k: index.append(1))
    p = FIX / "_tmp_page.html"
    p.write_text(html, encoding="utf-8")
    try:
        monkeypatch.setattr(sys, "argv", ["scraper.py", "--html", str(p)])
        assert scraper.main() == 1  # сбой виден (health считает), но второй день всё равно разобран
    finally:
        p.unlink()
    assert done == ["2026-11-04"] and index == [1]
    assert "ОШИБКА 2026-11-03" in capsys.readouterr().err


def test_week_doubt():
    """Номер недели в заголовке не совпал с расчётом от опорной даты — сомнение (сайт верит расчёту)."""
    assert scraper.expected_week("2026-11-02") == 1 and scraper.expected_week("2026-10-31") == 2
    assert scraper.week_doubt("2026-11-02", "Понедельник, 1-я неделя") is False
    assert scraper.week_doubt("2026-11-02", "Понедельник, 2-я неделя") is True
    assert scraper.week_doubt("2026-11-02", "") is False


@needs_tesseract
def test_table_continues_on_second_image(tmp_path):
    """Таблица на двух картинках, на второй нет шапки «группа / урок» — строки второй тоже читаются."""
    from PIL import Image
    import numpy as np
    im = Image.open(FIX / "27.10.2026.png").convert("L")
    full = scraper.ocr_table(FIX / "27.10.2026.png", scraper.subject_vocab())
    hl = [(s + e) // 2 for s, e in scraper._runs((np.array(im) < 128).mean(1) > 0.5)]
    cut = hl[-5]  # граница строки: последние 4 строки — на вторую картинку
    im.crop((0, 0, im.width, cut + 2)).save(tmp_path / "a.png")
    im.crop((0, cut - 1, im.width, im.height)).save(tmp_path / "b.png")
    a = scraper.ocr_table(tmp_path / "a.png", scraper.subject_vocab())
    b = scraper.ocr_table(tmp_path / "b.png", scraper.subject_vocab(), continued=True)
    key = lambda rows: [(r["lessons"], r["subject"], r["room"]) for r in rows]
    assert a["ok"] and b["ok"] and key(a["rows"] + b["rows"]) == key(full["rows"])
    assert scraper.ocr_table(tmp_path / "b.png", scraper.subject_vocab())["rows"] == []  # без continued — как раньше


def test_week_numbering_follows_college(tmp_path):
    """Нумерация недель сменилась: распоряжения двух недель подряд, номера чередуются и не сходятся с расчётом —
    опорная неделя переносится, и пишется заметка для задачи. Забытый шаблон (три дня одной недели) — не переносится."""
    z, g = tmp_path / "zameny", tmp_path / "groups"
    z.mkdir(), g.mkdir()
    (g / "11a.json").write_text(json.dumps({"week_anchor": {"date": "2026-10-19", "week": 1}, "days": {}}), encoding="utf-8")
    def day(date, week):
        (z / f"{date}.json").write_text(json.dumps({"date": date, "title": f"День, {week}-я неделя", "week_doubt": True}), encoding="utf-8")
    quiet = lambda *_: None
    # по расчёту 26–28.10 — 2-я неделя; в шаблоне забыли поменять «1-я» — три дня одной недели
    day("2026-10-26", 1), day("2026-10-27", 1), day("2026-10-28", 1)
    assert not scraper.fix_week_anchor(z, g, log=quiet)
    # следующая неделя (по расчёту 1-я) — снова «1-я»: номера не чередуются, это всё ещё не смена нумерации
    day("2026-11-02", 1), day("2026-11-03", 1)
    assert not scraper.fix_week_anchor(z, g, log=quiet)
    # смена: неделя 02.11 — «2-я», неделя 09.11 — «1-я» (по расчёту 1-я и 2-я)
    for p in z.glob("*.json"):
        p.unlink()
    day("2026-11-05", 2), day("2026-11-06", 2), day("2026-11-09", 1)
    assert scraper.fix_week_anchor(z, g, log=quiet)
    assert json.loads((g / "11a.json").read_text(encoding="utf-8"))["week_anchor"] == {"date": "2026-11-09", "week": 1}
    assert "нумерация недель" in (tmp_path / "notices.txt").read_text(encoding="utf-8")
    assert json.loads((z / "2026-11-09.json").read_text(encoding="utf-8"))["week_doubt"]  # пометку не снимаем


def test_date_without_year_near_new_year(monkeypatch):
    """«на 2 января» без года, выложено 30 декабря — это следующий год."""
    class D(scraper.dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 12, 30, 15, 0, tzinfo=tz)
    monkeypatch.setattr(scraper.dt, "datetime", D)
    blocks = scraper.parse_page('<div itemprop="articleBody"><p>на 2 января, очное отделение</p><img src="/i/a.png"></div>')
    assert blocks[0]["date"] == "2027-01-02"


def test_manual_corrections_survive_and_expire(tmp_path):
    """Ручная поправка замен накладывается поверх распознавания, пока картинка та же; перезалили — заметка человеку."""
    pop = {"days": {"2026-10-31": {"images": ["aaa"], "note": "сверено", "title": "Суббота, 2-я неделя",
                                    "all_changes": {"21-П": [{"lessons": [7, 8], "time": None, "subject": "Отменить", "room": "", "uncertain": False}]}}}}
    meta = {"date": "2026-10-31", "images": [{"sha1": "aaa"}], "title": "", "all_changes": {"21-Д": []}, "ocr_uncertain": True}
    scraper.apply_manual(meta, pop, tmp_path / "n.txt")
    assert list(meta["all_changes"]) == ["21-П"] and not meta["ocr_uncertain"] and meta["checked_by_hand"] == "сверено"
    meta2 = {"date": "2026-10-31", "images": [{"sha1": "bbb"}], "title": "", "all_changes": {"21-Д": []}}
    scraper.apply_manual(meta2, pop, tmp_path / "n.txt")
    assert list(meta2["all_changes"]) == ["21-Д"] and meta2["manual_outdated"]
    assert "перезалила" in (tmp_path / "n.txt").read_text(encoding="utf-8")


def test_section_words():
    """«Срочно», «досрочно» — не очное отделение; «очное», «заочного» — да."""
    html = """<div itemprop="articleBody"><p>на 3 ноября 2026 года заочное отделение</p><img src="/i/z1.png">
      <p>Срочно ознакомьтесь, досрочно</p><img src="/i/z2.png">
      <p>на 3 ноября 2026 года очное отделение</p><img src="/i/o.png"></div>"""
    got = {b["section"]: [i.rsplit("/", 1)[1] for i in b["images"]] for b in scraper.parse_page(html)}
    assert got == {"zaochnoe": ["z1.png", "z2.png"], "ochnoe": ["o.png"]}
