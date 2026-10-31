"""Скачивает страницу «Замена уроков» УТЖТ, сохраняет картинки замен
(очное отделение) и распознаёт в них строки всех групп (all_changes; сайт берёт строки своей группы оттуда).

Результат: data/zameny/<YYYY-MM-DD>.json + картинки data/zameny/<YYYY-MM-DD>-<n>.png
и сводный data/zameny/index.json, который читает сайт.

    python scraper.py                 # живой сайт
    python scraper.py --html page.html --offline   # разбор сохранённой страницы
    python scraper.py --ocr картинка.png           # распознать одну картинку
"""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import numpy as np
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

URL = "https://utgt-pgups.ru/ochnoe-zaochnoe-otdelenie/58-zamena-zanyatij.html"
TZ = ZoneInfo("Europe/Moscow")  # Ухта живёт по московскому времени
ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "data" / "zameny"
KEEP_DAYS = 21

MONTHS = {m: i + 1 for i, m in enumerate(
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split())}

# Все группы очного отделения из шапки расписания на семестр
KNOWN_GROUPS = ["11-П", "11-Д", "11-А", "11-С", "11-В", "11-Л",
                "21-П", "21-Д", "21-А", "21-С", "21-Л",
                "31-П", "31-Д", "31-А", "31-С",
                "41-П", "41-Д", "41-А", "41-С"]
# Как tesseract путает буквы групп. Цифру вместо буквы («11-1», «21-7») не угадываем: на мелких картинках
# так читаются и «Д», и «П» — пусть решают другие чтения той же ячейки.
LETTER_FIX = {"п": "П", "д": "Д", "а": "А", "a": "А", "с": "С",
              "c": "С", "©": "С", "в": "В", "b": "В", "л": "Л"}

CANCEL = "Отменить"
EXTRA_SUBJECTS = [CANCEL, "Разговоры о важном", "Химия", "Обществознание", "Биология",
                  "Физическая культура", "Русский язык", "Литература", "История",
                  "История России", "География", "Информатика", "Математика", "Физика",
                  "Иностранный язык (английский)", "Иностранный язык (немецкий)",
                  "Основы безопасности и защиты Родины", "Индивидуальный проект",
                  "Иностранный язык в профессиональной деятельности (английский)",
                  "Иностранный язык в профессиональной деятельности (немецкий)"]

UA = {"User-Agent": "Mozilla/5.0 (utgt schedule bot; +https://github.com/raspisanie-utgt/raspisanie-utgt.github.io)"}


# ---------- разбор HTML ----------

def parse_page(html, base_url=URL):
    """Возвращает [{date, section, images}] в порядке страницы."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".com-content-article__body") or soup.select_one("[itemprop=articleBody]")
    if body is None:
        raise ValueError("на странице не найден блок статьи")
    today = dt.datetime.now(TZ).date()
    blocks, date, section = [], None, None
    for el in body.find_all(["p", "div", "h1", "h2", "h3", "h4", "img"]):
        if el.name == "img":
            if date and section:
                src = urljoin(base_url, el.get("src", "").split("#")[0])
                key = (date, section)
                if not blocks or (blocks[-1]["date"], blocks[-1]["section"]) != key:
                    blocks.append({"date": date, "section": section, "images": []})
                if src not in blocks[-1]["images"]:
                    blocks[-1]["images"].append(src)
            continue
        if el.find(["p", "div"]):
            continue  # берём только листовые абзацы, чтобы текст не дублировался
        text = " ".join(el.get_text(" ").split()).lower()
        m = re.search(r"на\s+(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?", text)
        if m and m.group(2) in MONTHS:
            year = int(m.group(3)) if m.group(3) else today.year
            try:
                date = dt.date(year, MONTHS[m.group(2)], int(m.group(1))).isoformat()
            except ValueError:  # опечатка на странице («на 31 ноября») — пропускаем, остальное разбираем
                print(f"ВНИМАНИЕ: неверная дата на странице: «{m.group(0)}»", file=sys.stderr)
                date = None
            section = None
        if "заочн" in text:
            section = "zaochnoe"
        elif "очн" in text:
            section = "ochnoe"
        if "по расписанию" in text and date and section:
            # вместо картинки написано «по расписанию» — замен в этот день нет
            if not blocks or (blocks[-1]["date"], blocks[-1]["section"]) != (date, section):
                blocks.append({"date": date, "section": section, "images": []})
    # одна дата и отделение встретились на странице дважды («дополнение» ниже) — один блок со всеми картинками,
    # иначе второй затирал бы первый (тот же <дата>.json), и каждый час они менялись бы местами
    merged = {}
    for b in blocks:
        m = merged.setdefault((b["date"], b["section"]), {"date": b["date"], "section": b["section"], "images": []})
        m["images"] += [i for i in b["images"] if i not in m["images"]]
    return list(merged.values())


def write_atomic(path, data):
    """Запись через временный файл: прерванный запуск не оставит полузаписанный файл."""
    tmp = path.with_name(path.name + ".tmp")
    if isinstance(data, bytes):
        tmp.write_bytes(data)
    else:
        tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


# ---------- распознавание таблицы ----------

def _runs(mask):
    out, start = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    return out


def _tesseract(img, psm, lang="rus", extra=()):
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        img.save(f.name)
        r = subprocess.run(["tesseract", f.name, "-", "-l", lang, "--psm", str(psm), *extra],
                           capture_output=True, text=True, check=True)
    return " ".join(r.stdout.split())


# только цифры и дефис: на мелких картинках «7-8» иначе читается как «1-8», «8-30» — как «8-50»
DIGITS = ("-c", "tessedit_char_whitelist=0123456789-")


VOTE_SHARE = 0.6  # доля согласных прочтений, чтобы считать ответ уверенным (подобрано: tools/ocr_proverka.py)
ROOM_ALT_MIN = 1  # сколько прочтений должно быть за другой кабинет, чтобы считать кабинет спорным


def _vote(values):
    """Самое частое из прочитанного (None — не прочиталось) и уверенность: за него не меньше VOTE_SHARE прочтений.
    Одно и то же место читаем по-разному — так случайная ошибка не проходит, а расхождение видно."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None, False
    best, n = Counter(vals).most_common(1)[0]
    return best, n >= VOTE_SHARE * len(vals)


def normalize_group(text):
    """'11-А' / '11-7' / '21-С©' -> ('11-А'|..., ok). None, если в ячейке нет группы."""
    s = re.sub(r"[\]\[|)(}{'\".,]", "", text)
    s = re.sub(r"[\s—–_]+", "-", s.strip())
    m = re.search(r"([1-4])1-*(\S)", s)
    if not m:
        return None, not re.search(r"\d", text)
    letter = LETTER_FIX.get(m.group(2), LETTER_FIX.get(m.group(2).lower(), m.group(2).upper()))
    group = f"{m.group(1)}1-{letter}"
    return (group, True) if group in KNOWN_GROUPS else (group, False)


def known_rooms():
    """Кабинеты из расписаний групп и data/rooms.json — чтобы ловить мусор распознавания."""
    rooms = set()
    for path in sorted((ROOT / "data" / "groups").glob("*.json")):
        sched = json.loads(path.read_text(encoding="utf-8"))
        for day in sched.get("days", {}).values():
            for l in day:
                rooms |= {r.strip() for r in str(l.get("room") or "").split(" / ") if r.strip()}
    extra = ROOT / "data" / "rooms.json"
    if extra.exists():
        extra_data = json.loads(extra.read_text(encoding="utf-8"))
        rooms |= set(extra_data.get("rooms", {})) | set(extra_data.get("other_rooms", []))
    return rooms


def snap_room(room, known):
    """Черта таблицы сразу за номером читается как «1»: «1-8|» -> «1-81». Такого кабинета нет,
    а «1-8» есть — берём его."""
    if room and known and room not in known and room[-1].isdigit() and room[:-1] in known:
        return room[:-1]
    return room


def fix_digits(text):
    """OCR путает цифры в номере кабинета: «2-]2» -> «2-12», «1-З» -> «1-3»."""
    return text.translate(str.maketrans({"]": "1", "[": "1", "|": "1", "l": "1", "I": "1", "З": "3", "О": "0", "о": "0"}))


def parse_lessons(text):
    """'5-6' -> ([5, 6], None); '8-30' -> ([0], '08:30') ; '3' -> ([3], None).
    Дефис потерялся: '34' -> ([3, 4], None), '910' -> ([9, 10], None), '830' -> ([0], '08:30')."""
    t = text.replace("—", "-").replace("–", "-").replace(":", "-")
    m = re.fullmatch(r"\s*(\d{2,4})\s*", t)
    if m and m.group(1) != "10":
        d = m.group(1)
        if d == "910":
            return [9, 10], None
        if len(d) == 2 and 1 <= int(d[0]) < int(d[1]) <= 9:
            return list(range(int(d[0]), int(d[1]) + 1)), None
        if len(d) >= 3 and int(d[-2:]) < 60 and 8 <= int(d[:-2]) <= 18:
            time = f"{int(d[:-2]):02d}:{d[-2:]}"
            return ([0] if time == "08:30" else []), time
    nums = [int(n) for n in re.findall(r"\d{1,2}", t)]
    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        if b > 10:  # это время начала, а не номера уроков
            time = f"{a:02d}:{b:02d}"
            return ([0] if time == "08:30" else []), time
        if 1 <= a <= b <= 10:
            return list(range(a, b + 1)), None
    if len(nums) == 1 and re.search(r"\d\s*-+\s*$", t) and nums[0] % 2 == 1:
        return [nums[0], nums[0] + 1], None  # «3-» — вторая цифра не распозналась
    if len(nums) == 1 and 1 <= nums[0] <= 10:
        return [nums[0]], None
    return [], None


SUBJ_CODE = re.compile(r"^\s*(МДК|ПМ|ОП|ОГСЭ|ЕН|УП|ПП|ПДП|ОУД|УД|СГ|ОД|ПД)[.\s]*(\d+(?:[.\s]+\d+)*)", re.I)


def subject_code(s):
    """«МДК.03.01 Обеспечение…» -> «МДК.03.01»; без кода — None."""
    m = SUBJ_CODE.match(s or "")
    return m.group(1).upper() + "." + re.sub(r"[.\s]+", ".", m.group(2)) if m else None


def snap_subject(text, vocab):
    if not text:
        return text, True
    best = difflib.get_close_matches(text, vocab, n=1, cutoff=0.75)
    if best:
        # похожие МДК различаются только цифрой кода («03.01» и «03.02»): если код прочитан и не совпал —
        # берём название, но строка неуверенная (цифра могла прочитаться неверно)
        a, b = subject_code(text), subject_code(best[0])
        if a and b and a != b:
            same = [v for v in vocab if subject_code(v) == a]
            if same:
                return difflib.get_close_matches(text, same, n=1, cutoff=0)[0], True
            return best[0], False
        return best[0], True
    if difflib.SequenceMatcher(None, text.lower()[:9], CANCEL.lower()).ratio() > 0.7:
        return CANCEL, True
    if text.lower().startswith(("разгов", "разтов", "разговоры")):
        return "Разговоры о важном", True
    return text, False


def ocr_table(path, vocab=EXTRA_SUBJECTS, rooms=None, continued=False):
    """Находит сетку таблицы и распознаёт её построчно, ячейка за ячейкой.
    continued — картинка продолжает таблицу с предыдущей картинки того же дня: шапки «группа / урок» на ней
    может не быть, строки идут сразу."""
    rooms = known_rooms() if rooms is None else rooms
    im = Image.open(path).convert("L")
    ink = np.array(im) < 128
    hlines = [(s + e) // 2 for s, e in _runs(ink.mean(1) > 0.5)]
    # на картинке может быть всё распоряжение: длинные линии бланка над таблицей мешают найти столбцы —
    # берём самую большую группу близко стоящих линий (это и есть таблица)
    if len(hlines) > 3:
        step, groups = np.median(np.diff(hlines)), [[hlines[0]]]
        for a, b in zip(hlines, hlines[1:]):
            if b - a > 4 * step:
                groups.append([])
            groups[-1].append(b)
        best = max(groups, key=len)
        if len(best) >= 3:
            hlines = best
    if len(hlines) < 3:
        return {"ok": False, "error": "таблица не найдена", "rows": []}
    band = ink[hlines[0]:hlines[-1]]
    vlines = [(s + e) // 2 for s, e in _runs(band.mean(0) > 0.6)]
    if len(vlines) < 4:
        return {"ok": False, "error": "не найдены столбцы таблицы", "rows": []}
    row_h = np.median(np.diff(hlines))
    scale = max(3, int(round(66 / max(row_h, 1))))

    def cell(x0, x1, y0, y1, psm, k=None, pad=False, lang="rus", extra=()):
        c = im.crop((x0 + 2, y0 + 2, x1 - 1, y1 - 1))
        # пусто ли: считаем и серые точки — мелкий размытый текст бывает совсем не чёрным,
        # и «11-В» иначе принимается за пустую ячейку (строка молча уходит предыдущей группе)
        dark = (np.array(c) < 192).mean() if c.width > 4 and c.height > 4 else 0
        if dark < 0.004:
            return "", dark
        k = k or scale
        c = c.resize((c.width * k, c.height * k), Image.LANCZOS)
        if pad:  # белое поле вокруг: мелкие буквы у самой рамки ячейки иначе путаются (П -> И, 7 -> 1)
            c = ImageOps.expand(c, border=c.height // 2, fill=255)
        return _tesseract(c, psm, lang, extra), dark

    title, rows, in_table, group, group_doubt = "", [], continued, None, False
    group_sure = True  # группа текущего блока прочитана уверенно — следующие строки блока наследуют это
    for y0, y1 in zip(hlines, hlines[1:]):
        if y1 - y0 < 8:
            continue
        texts = [cell(x0, x1, y0, y1, 6 if i == 2 else 7) for i, (x0, x1) in enumerate(zip(vlines, vlines[1:]))]
        raw = [t for t, _ in texts]
        joined = " ".join(raw).lower()
        header = "урок" in joined and ("групп" in joined or "трупп" in joined)
        if not in_table or header or ("недел" in joined and not re.search(r"\d", raw[1] if len(raw) > 1 else "")):
            if "недел" in joined:
                title = next(t for t in raw if "недел" in t.lower())
            if header:
                in_table = True
            continue
        g_text, g_dark = texts[0]
        g, g_ok = normalize_group(g_text)
        g_ink = g_dark >= 0.004  # в ячейке группы что-то есть (даже если прочиталась пустота)
        if g_ink:
            # ещё два чтения с белым полем; группа — за которую большинство настоящих прочтений
            reads = [g_text] + [cell(vlines[0], vlines[1], y0, y1, 7, k, pad=True)[0] for k in (4, 5)]
            g_text = " ".join(r for r in reads if r)
            known = [n for n, ok in map(normalize_group, reads) if n and ok]
            best, sure = _vote(known)
            if best:
                g, g_ok = best, sure
            for k in (3, 5, 2):  # ничего не прочиталось как группа — пробуем другой масштаб
                if g and g_ok:
                    break
                g2, ok2 = normalize_group(cell(vlines[0], vlines[1], y0, y1, 7, k)[0])
                if g2 and (ok2 or not g):
                    g, g_ok = g2, ok2
        row_uncertain = False
        if g:
            group, group_sure = g, g_ok
            group_doubt |= not g_ok  # название группы прочитано криво — строка может быть чьей угодно
        elif not g_ok or re.search(r"[0-9А-Яа-яA-Za-z]", g_text) or (g_ink and not g_text and g_dark > 0.03):
            # в ячейке группы что-то написано, но прочитать не вышло:
            # не приписываем строку предыдущей группе молча
            group, group_sure, group_doubt = "?", False, True
        if group is None:  # первая строка таблицы, а группа не прочиталась — не терять строку молча
            group, group_sure, group_doubt = "?", False, True
        row_uncertain = not group_sure
        # урок: обычное чтение и ещё четыре разными способами (подобраны на мелких картинках 19.10–02.11:
        # каждый способ где-то ошибается, большинство — нет); берём то, за что большинство
        lesson_reads = [raw[1] if len(raw) > 1 else ""]
        if lesson_reads[0]:
            lesson_reads += [cell(vlines[1], vlines[2], y0, y1, 7, k, pad=True, lang=lang, extra=extra)[0]
                             for k, lang, extra in ((5, "eng", DIGITS), (3, "eng", DIGITS), (4, "rus", DIGITS), (4, "rus", ()))]
        parsed = [(tuple(l), t) for l, t in map(parse_lessons, lesson_reads)]
        best, lessons_sure = _vote([p for p in parsed if p[0] or p[1]])
        lessons, time = (list(best[0]), best[1]) if best else ([], None)
        if best and not lessons_sure:
            row_uncertain = True
        subject = raw[2] if len(raw) > 2 else ""
        room = fix_digits(raw[3]) if len(raw) > 3 else ""
        room_alts = []
        if len(raw) > 3 and re.match(r"\s*ак", raw[3], re.I):  # «АкКтТ.ЗАЛ»
            room = "Акт. зал"
        elif len(raw) > 3 and raw[3]:
            # кабинет: несколько масштабов; «]» в конце — это 7 или 1 (на мелкой картинке не различить)
            room_reads = [raw[3]] + [cell(vlines[3], vlines[4], y0, y1, 7, k, pad=pad)[0] for k, pad in ((3, False), (6, False), (4, True))]
            votes = Counter()
            for r in room_reads:
                r = r.replace(" ", "")
                variants = {snap_room(fix_digits(r), rooms), snap_room(fix_digits(r.replace("]", "7")), rooms)}
                votes.update(v for v in variants if v in rooms)
            if votes:
                room_alts = [v for i, (v, n) in enumerate(votes.most_common()) if i == 0 or n >= ROOM_ALT_MIN]
                room = room_alts[0]  # прочтения расходятся — решит сверка (check_with_schedule)
        if not re.search(r"\d-\d", room) and room != "Акт. зал":
            m = re.search(r"\s*[|\]]?\s*(\d-\d{1,2})\s*$", subject)
            room = m.group(1) if m else ""
            if m:
                subject = subject[:m.start()]
        room = snap_room(room, rooms)
        subject = subject.strip(" |]")
        subject, s_ok = snap_subject(subject, vocab)
        if not subject and texts[2][1] > 0.01:  # в ячейке что-то написано, а прочиталась пустота
            s_ok = False
        if not lessons and not time:
            row_uncertain = True
        if len(lessons) >= 7 and lessons[0] == 1:  # «1-8» на мелкой картинке — обычно неверно прочитанное «7-8»
            row_uncertain = True
        if len(lessons) > 1 and (lessons[0] % 2 == 0 or lessons[-1] % 2 == 1):
            row_uncertain = True  # пары — с нечётного урока по чётный: «1-5», «4-6» — скорее всего, цифра прочитана неверно
        if not room and len(texts) > 3 and texts[3][1] > 0.01:
            row_uncertain = True  # в ячейке кабинета что-то написано, а кабинет не прочитался
        rows.append({"group": group, "lessons": lessons, "time": time, "subject": subject,
                     "room": room, "uncertain": row_uncertain or not s_ok, "raw": raw,
                     "room_alts": room_alts if len(room_alts) > 1 else []})
    return {"ok": in_table and bool(rows), "title": title, "rows": rows,
            # рамка таблицы на картинке: сайт показывает только её, крупно (x0, y0, x1, y1, ширина, высота)
            "box": [int(vlines[0]), int(hlines[0]), int(vlines[-1]), int(hlines[-1]), im.width, im.height],
            "group_doubt": group_doubt,
            "error": None if in_table else "не найдена шапка таблицы", "in_table": in_table}


def expected_week(date, anchor=None):
    """Номер недели (1/2) по расчёту от опорной даты расписания — как weekNumber в site/agenda.js."""
    if anchor is None:
        anchor = json.loads((ROOT / "data" / "groups" / "11a.json").read_text(encoding="utf-8")).get("week_anchor")
    if not anchor:
        return None
    weeks = (dt.date.fromisoformat(date) - dt.date.fromisoformat(anchor["date"])).days // 7
    return anchor["week"] if weeks % 2 == 0 else 3 - anchor["week"]


def title_week(title):
    m = re.search(r"([12])\s*-?\s*я\s+недел", title or "")
    return int(m.group(1)) if m else None


def week_doubt(date, title):
    t, e = title_week(title), expected_week(date)
    return bool(t and e and t != e)


def check_with_schedule(tables, date, title="", schedules=None, past=None):
    """Сверка распознанного с расписанием групп и прошлыми заменами (меняет строки на месте):
    - кабинет прочитался по-разному (ничья) — берём тот, что у группы по этому предмету в расписании
      или в прошлых распоряжениях; не нашёлся — строка неуверенная;
    - отменяют уроки, которых у группы в этот день по расписанию нет, — скорее всего, неверно
      прочитана группа или номера уроков: строка неуверенная."""
    if schedules is None:
        idx = json.loads((ROOT / "data" / "groups" / "index.json").read_text(encoding="utf-8"))
        schedules = {g["group"]: json.loads((ROOT / "data" / "groups" / g["file"]).read_text(encoding="utf-8"))
                     for g in idx["groups"]}
    if past is None:
        past = past_rooms(before=date)
    wd = dt.date.fromisoformat(date).isoweekday()
    week = expected_week(date) or title_week(title)  # заголовок распознаётся один раз — верим расчёту
    for t in tables:
        for r in t["rows"]:
            s = schedules.get(r["group"])
            alts = r.pop("room_alts", None) or []
            if not s:
                if len(alts) > 1:
                    r["uncertain"] = True
                continue
            if len(alts) > 1:
                own = {e["room"] for d in s["days"].values() for e in d if e["subject"] == r["subject"]}
                hits = [a for a in alts if a in own] or [a for a in alts if a in past.get((r["group"], r["subject"]), ())]
                if len(hits) == 1:
                    r["room"] = hits[0]
                else:
                    r["uncertain"] = True  # прочтения расходятся, и расписание не подсказывает
            day = [e for e in s["days"].get(str(wd), []) if not (e.get("week") and week and e["week"] != week)]
            have = {n for e in day for n in e["lessons"]}
            if r["subject"] == CANCEL and r["lessons"] and not set(r["lessons"]) & have:
                r["uncertain"] = True
    return tables


def past_rooms(before=None, archive=ROOT / "data" / "archive"):
    """Кабинеты из прошлых распоряжений: {(группа, предмет): {кабинеты}} — чтобы решать ничью по кабинету."""
    import gzip
    out = {}
    for p in sorted(archive.glob("????-??.json.gz")):
        for date, z in json.loads(gzip.decompress(p.read_bytes()).decode("utf-8")).items():
            if before and date >= before:
                continue
            for g, rows in (z.get("all_changes") or {}).items():
                for r in rows:
                    if r.get("room") and not r.get("uncertain"):
                        out.setdefault((g, r["subject"]), set()).add(r["room"])
    return out


def ocr_uncertain(tables, all_changes):
    """Что-то в распоряжении распознано неуверенно (у любой группы) — сайт попросит сверить с картинкой."""
    return any(t.get("group_doubt") for t in tables) or any(r["uncertain"] for rows in all_changes.values() for r in rows)


def group_changes(table, group):
    return [{k: r[k] for k in ("lessons", "time", "subject", "room", "uncertain")}
            for r in table["rows"] if r["group"] == group]


def all_group_changes(tables):
    """Строки замен по всем группам: {"21-С": [...], ...}; «?» — группа не распозналась."""
    out = {}
    for t in tables:
        for r in t["rows"]:
            if r["group"]:
                out.setdefault(r["group"], []).append(
                    {k: r[k] for k in ("lessons", "time", "subject", "room", "uncertain")})
    return out


# ---------- сохранение ----------

def subject_vocab():
    names = set()
    for path in sorted((ROOT / "data" / "groups").glob("*.json")):
        sched = json.loads(path.read_text(encoding="utf-8"))
        names |= {l["subject"] for day in sched.get("days", {}).values() for l in day}
    return sorted(names | set(EXTRA_SUBJECTS))


def process_block(block, session, vocab, out_dir=OUT_DIR, log=print):
    """Скачивает картинки дня, распознаёт, пишет <date>.json. True, если что-то изменилось."""
    date = block["date"]
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / f"{date}.json"
    old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None

    images, blobs = [], []
    for i, url in enumerate(block["images"], 1):
        r = session.get(url, timeout=60, headers=UA)
        r.raise_for_status()
        blobs.append(r.content)
        images.append({"url": url, "file": f"{date}-{i}.png", "sha1": hashlib.sha1(r.content).hexdigest()})
    if old and [i["sha1"] for i in old["images"]] == [i["sha1"] for i in images]:
        log(f"{date}: без изменений")
        return False

    tables = []
    for img, blob in zip(images, blobs):
        write_atomic(out_dir / img["file"], blob)
        # шапка уже нашлась на предыдущей картинке дня — эта может быть продолжением таблицы без шапки
        t = ocr_table(out_dir / img["file"], vocab, continued=any(x.get("in_table") for x in tables))
        if t.get("box"):
            img["table"] = t["box"]
        tables.append(t)
    check_with_schedule(tables, date, next((t["title"] for t in tables if t.get("title")), ""))
    all_changes = all_group_changes(tables)
    meta = {
        "date": date,
        "source": URL,
        "fetched_at": dt.datetime.now(TZ).isoformat(timespec="minutes"),
        # когда распоряжение впервые появилось на сайте техникума (по нашим проверкам; не меняется,
        # даже если потом перевыложат исправленное) — для tools/publish_times.py
        "first_seen": (old or {}).get("first_seen") or (old or {}).get("fetched_at") or dt.datetime.now(TZ).isoformat(timespec="minutes"),
        # распоряжение перевыложили (картинки другие): когда и какими были замены до исправления —
        # сайт покажет «Замены обновлены» и что именно поменялось у группы
        "updated_at": dt.datetime.now(TZ).isoformat(timespec="minutes") if old else None,
        "prev_all_changes": (old.get("all_changes") or {}) if old else None,
        "images": images,
        "title": next((t["title"] for t in tables if t.get("title")), ""),
        "po_raspisaniyu": not images,
        "ocr_ok": all(t["ok"] for t in tables),
        "ocr_uncertain": ocr_uncertain(tables, all_changes),
        "ocr_group_doubt": any(t.get("group_doubt") for t in tables),
        # номер недели в заголовке не совпал с расчётом: сайт верит расчёту и просит сверить с картинкой
        "week_doubt": week_doubt(date, next((t["title"] for t in tables if t.get("title")), "")),
        "groups_in_order": sorted({r["group"] for t in tables for r in t["rows"] if r["group"]}),
        "all_changes": all_changes,
    }
    write_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=1))
    log(f"{date}: {len(images)} картинок, групп с заменами {len(all_changes)}, ocr_ok={meta['ocr_ok']}")
    return True


def reprocess(out_dir=OUT_DIR, vocab=None, log=print):
    """Заново распознать уже сохранённые картинки (после улучшений OCR)."""
    vocab = vocab or subject_vocab()
    for path in sorted(out_dir.glob("????-??-??.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        if not meta["images"]:
            continue
        tables = []
        for i in meta["images"]:
            tables.append(ocr_table(out_dir / i["file"], vocab, continued=any(x.get("in_table") for x in tables)))
        check_with_schedule(tables, meta["date"], next((t["title"] for t in tables if t.get("title")), ""))
        for i, t in zip(meta["images"], tables):
            if t.get("box"):
                i["table"] = t["box"]
        all_changes = all_group_changes(tables)
        meta.pop("group", None)
        meta.pop("changes", None)
        meta.update(title=next((t["title"] for t in tables if t.get("title")), "") or meta.get("title", ""),
                    ocr_ok=all(t["ok"] for t in tables),
                    ocr_uncertain=ocr_uncertain(tables, all_changes),
                    ocr_group_doubt=any(t.get("group_doubt") for t in tables),
                    week_doubt=week_doubt(meta["date"], next((t["title"] for t in tables if t.get("title")), "")),
                    groups_in_order=sorted({r["group"] for t in tables for r in t["rows"] if r["group"]}),
                    all_changes=all_changes)
        write_atomic(path, json.dumps(meta, ensure_ascii=False, indent=1))
        log(f"{meta['date']}: групп с заменами {len(all_changes)}")


def write_index(out_dir=OUT_DIR, today=None):
    today = today or dt.datetime.now(TZ).date()
    for p in out_dir.glob("*-*-*.*"):
        d = p.name[:10]
        try:
            if (today - dt.date.fromisoformat(d)).days > KEEP_DAYS:
                p.unlink()
        except ValueError:
            pass
    days = sorted(json.loads(p.read_text(encoding="utf-8"))["date"] for p in out_dir.glob("????-??-??.json"))
    index = {"source": URL, "days": days}
    old = (out_dir / "index.json").read_text(encoding="utf-8") if (out_dir / "index.json").exists() else ""
    new = json.dumps(index, ensure_ascii=False, indent=1)
    if old != new:
        write_atomic(out_dir / "index.json", new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="разобрать сохранённую страницу вместо скачивания")
    ap.add_argument("--offline", action="store_true", help="только показать найденные блоки")
    ap.add_argument("--ocr", help="распознать одну картинку и вывести таблицу")
    ap.add_argument("--reprocess", action="store_true", help="заново распознать сохранённые картинки")
    args = ap.parse_args()

    if args.reprocess:
        reprocess()
        return 0

    if args.ocr:
        t = ocr_table(args.ocr, subject_vocab())
        print(json.dumps(t, ensure_ascii=False, indent=1))
        return 0

    session = requests.Session()
    if args.html:
        html = Path(args.html).read_text(encoding="utf-8")
    else:
        r = session.get(URL, timeout=60, headers=UA)
        r.raise_for_status()
        r.encoding = "utf-8"
        html = r.text
    blocks = parse_page(html)
    ochnoe = [b for b in blocks if b["section"] == "ochnoe"]
    print("на странице:", ", ".join(f"{b['date']} ({b['section']}, {len(b['images'])} карт.)" for b in blocks) or "ничего")
    if not ochnoe:
        print("ВНИМАНИЕ: замены для очного отделения не найдены — возможно, поменялась вёрстка", file=sys.stderr)
    if args.offline:
        return 0
    vocab = subject_vocab()
    failed = []
    try:
        for b in ochnoe:
            try:  # одна битая картинка (например, старого дня) не мешает разобрать остальные дни
                process_block(b, session, vocab)
            except Exception as e:  # noqa: BLE001
                failed.append(b["date"])
                print(f"ОШИБКА {b['date']}: {e!r}", file=sys.stderr)
    finally:
        write_index()
    # страница открылась, но замен не нашлось — для мониторинга это сбой (скорее всего, вёрстка);
    # ошибка — только если не удалось вообще ничего
    if not ochnoe:
        return 2
    return 1 if len(failed) == len(ochnoe) else 0


if __name__ == "__main__":
    sys.exit(main())
