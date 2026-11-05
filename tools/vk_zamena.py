"""Замена, присланная в беседу ВК: фото -> распознавание -> файл дня -> сайт.

Кто что делает:
  * бот домашки (dz-bot, скрипт Гугла) ловит в беседе «Помощник 11-А» фото с словом
    «замена»/«распоряжение», кладёт картинку в репозиторий сайта (data/vk-incoming/)
    и запускает проверку сайта на GitHub;
  * эта проверка (scraper.py -> process_incoming) распознаёт картинку и, если всё прочиталось
    уверенно, публикует замену: data/zameny/<дата>.json и <дата>-1.png, список дней (index.json);
  * что получилось — пишется в data/vk-result.json; бот читает его и пишет владельцу в личку,
    а если распозналось сомнительно — ещё и открывает задачу в GitHub.

Дата замены — только с картинки («... на 06.11.2026 года»), как решил владелец.
Распознавание — тем же кодом, что и ежечасная проверка сайта (scraper.ocr_table).

Запуск вручную (для проверки):

    python tools/vk_zamena.py --file data/zameny/2026-11-06-1.png
    python tools/vk_zamena.py --url https://vk.com/photo-... --msg 12345
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import scraper  # noqa: E402

# месяцы распоряжения словами: «на 6 ноября 2026 года»
MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "май": 5, "мая": 5, "мае": 5,
          "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
MONTH_WORD = "|".join(sorted(MONTHS, key=len, reverse=True))
LABEL = "замена из ВК"
# сколько фото одного распоряжения берём (второй лист — продолжение таблицы)
MAX_PHOTOS = 3
# папка, куда бот кладёт присланные фото (в репозитории)
INCOMING = "vk-incoming"


# ---------- дата замены с картинки ----------

def _norm(text):
    """Текст в одну строку, без неразрывных пробелов."""
    return " ".join(str(text).replace("\u00a0", " ").split())


def _date(y, m, d):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def _month_num(word):
    for k, v in MONTHS.items():
        if word.startswith(k):
            return v
    return None


def find_dates(text):
    """Все даты в тексте: [(дата, стоит ли перед датой «на»)] — по порядку появления."""
    t = _norm(text).lower()
    found = []
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", t):
        d = _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            found.append((m.start(), d))
    for m in re.finditer(r"\b(\d{1,2})\s+(" + MONTH_WORD + r")[а-яё]*\s+(\d{4})\b", t):
        mon = _month_num(m.group(2))
        d = _date(int(m.group(3)), mon, int(m.group(1))) if mon else None
        if d:
            found.append((m.start(), d))
    found.sort()
    out = []
    for pos, d in found:
        before = t[max(0, pos - 40):pos]
        out.append((d, bool(re.search(r"(?:^|[\s,;:])на\s+$", before))))
    return out


def date_from_text(text, today=None):
    """Дата замены из текста распоряжения.

    Так записана дата замены: «... на 06.11.2026 года» (числом или словами) — берём такую дату.
    Если «на» нет, берём последнюю дату в тексте. Дата вне диапазона (30 дней назад ..
    45 дней вперёд) не подходит — значит, прочитали не то.
    """
    today = today or dt.datetime.now(scraper.TZ).date()
    cands = find_dates(text)
    if not cands:
        return None
    pref = [d for d, na in cands if na]
    pick = pref[-1] if pref else cands[-1][0]
    if not (today - dt.timedelta(days=30) <= pick <= today + dt.timedelta(days=45)):
        return None
    return pick.isoformat()


def ocr_text(path, psm=6, lang="rus"):
    """Распознанный текст картинки (tesseract)."""
    r = subprocess.run(["tesseract", str(path), "-", "-l", lang, "--psm", str(psm)],
                       capture_output=True, text=True, check=True)
    return r.stdout


def date_from_image(path, today=None):
    """Дата замены с картинки распоряжения и весь распознанный текст.

    Сначала верхняя часть листа (строка «на ... года» вверху), если там не нашлось — весь лист.
    """
    from PIL import Image
    with Image.open(path) as src:
        im = src.convert("RGB")
        top = im.crop((0, 0, im.width, int(im.height * 0.5)))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "top.png"
            top.save(p)
            text = ocr_text(p)
            date = date_from_text(text, today)
            if date:
                return date, text
    text = ocr_text(path, psm=3)
    return date_from_text(text, today), text


# ---------- решение: публиковать или задача ----------

def is_clean(meta):
    """Распознавание уверенное — можно публиковать на сайт."""
    return bool(meta.get("ocr_ok")
                and not meta.get("ocr_uncertain")
                and not meta.get("ocr_group_doubt")
                and not meta.get("week_doubt")
                and meta.get("groups_in_order"))


def why(meta):
    """Почему не публикуем — коротко, для задачи."""
    reasons = []
    if not meta.get("ocr_ok"):
        reasons.append("таблица не распозналась")
    if meta.get("ocr_uncertain"):
        reasons.append("есть неуверенно прочитанные строки")
    if meta.get("ocr_group_doubt"):
        reasons.append("не все группы прочитались")
    if meta.get("week_doubt"):
        reasons.append("неделя в заголовке не совпала с расчётом")
    if not meta.get("groups_in_order"):
        reasons.append("нет ни одной группы")
    return ", ".join(reasons) or "причина неясна"


# ---------- разбор фото ----------

def build_meta(date, images, tables, all_changes, title, now=None):
    """Файл дня — как у ежечасной проверки сайта, но из фото из беседы."""
    now = now or dt.datetime.now(scraper.TZ).isoformat(timespec="minutes")
    return {
        "date": date,
        "source": scraper.URL,
        "fetched_at": now,
        "first_seen": now,
        "updated_at": None,
        "prev_all_changes": None,
        "images": images,
        "title": title,
        "po_raspisaniyu": False,
        "ocr_ok": all(t.get("ok") for t in tables),
        "ocr_uncertain": scraper.ocr_uncertain(tables, all_changes),
        "ocr_group_doubt": any(t.get("group_doubt") for t in tables),
        "week_doubt": scraper.week_doubt(date, title),
        "groups_in_order": sorted({r["group"] for t in tables for r in t["rows"] if r.get("group")}),
        "all_changes": all_changes,
        "from_vk": True,
    }


def publish(files, out_dir=None, today=None, dry=False, log=print):
    """Распознать фото и, если всё чисто, опубликовать замену на сайте.

    files — пути к картинкам (первая — с шапкой распоряжения, остальные — продолжение таблицы).
    Возвращает результат: {status, date, groups, ...}.
    """
    out_dir = Path(out_dir) if out_dir else scraper.OUT_DIR
    today = today or dt.datetime.now(scraper.TZ).date()
    files = [Path(f) for f in files][:MAX_PHOTOS]

    date, text = None, ""
    for p in files:  # дата на первом листе, но если там не нашлось — посмотрим остальные
        d, t = date_from_image(p, today)
        text = text or t
        if d:
            date = d
            break
    if not date:
        return {"status": "no_date", "error": "на картинке не нашлась дата замены",
                "text": _norm(text)[:400]}

    meta_path = out_dir / ("%s.json" % date)
    if meta_path.exists():
        return {"status": "already", "date": date}

    vocab = scraper.subject_vocab()
    tables = []
    for p in files:
        tables.append(scraper.ocr_table(p, vocab, continued=any(x.get("in_table") for x in tables)))
    title = next((t["title"] for t in tables if t.get("title")), "")
    scraper.check_with_schedule(tables, date, title)
    all_changes = scraper.all_group_changes(tables)

    images = []
    for i, p in enumerate(files, 1):
        blob = p.read_bytes()
        ext = ".jpg" if blob[:2] == b"\xff\xd8" else ".png"
        images.append({"url": scraper.URL, "file": "%s-%d%s" % (date, i, ext),
                       "sha1": hashlib.sha1(blob).hexdigest()})

    meta = build_meta(date, images, tables, all_changes, title)
    scraper.apply_manual(meta)
    if not is_clean(meta):
        return {"status": "uncertain", "date": date, "groups": meta["groups_in_order"],
                "reason": why(meta), "text": _norm(text)[:1200]}
    if dry:
        return {"status": "ok", "date": date, "groups": meta["groups_in_order"], "dry": True}

    out_dir.mkdir(parents=True, exist_ok=True)
    for img, p in zip(images, files):
        scraper.write_atomic(out_dir / img["file"], p.read_bytes())
    scraper.write_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=1))
    scraper.write_index(out_dir)
    return {"status": "ok", "date": date, "groups": meta["groups_in_order"],
            "files": [i["file"] for i in images]}


def download(url, dest):
    """Скачать фото сообщения ВК."""
    r = requests.get(url, timeout=60, headers=scraper.UA)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def process_incoming(data_dir=None, out_dir=None, today=None, log=print):
    """Разобрать фото, присланные ботом в data/vk-incoming/.

    Вызывается из ежечасной проверки сайта (scraper.py) — до обращения к сайту техникума:
    если тот лежит, распоряжение из беседы всё равно попадёт на сайт.
    """
    data_dir = Path(data_dir) if data_dir else scraper.DATA
    out_dir = Path(out_dir) if out_dir else scraper.OUT_DIR
    incoming = data_dir / INCOMING
    if not incoming.is_dir():
        return []
    results = []
    for path in sorted(incoming.iterdir()):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        msg = path.stem
        try:
            res = publish([path], out_dir=out_dir, today=today, log=log)
        except Exception as e:
            res = {"status": "error", "error": str(e)[:300]}
        res["msg"] = msg
        results.append(res)
        log("замена из беседы ВК (%s): %s%s" % (msg, res.get("status"),
                                               (" за " + res["date"]) if res.get("date") else ""))
        # картинка разобрана — убрать её, чтобы не попала в сайт и не повторялась
        try:
            path.unlink()
        except OSError:
            pass
    if results:
        write_result(results[-1], data_dir)
    return results


def write_result(res, data_dir=None):
    """data/vk-result.json — что получилось; бот читает его и пишет владельцу в личку."""
    data_dir = Path(data_dir) if data_dir else scraper.DATA
    res = {k: v for k, v in res.items() if k != "meta"}
    res["at"] = dt.datetime.now(scraper.TZ).isoformat(timespec="minutes")
    path = data_dir / "vk-result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    scraper.write_atomic(path, json.dumps(res, ensure_ascii=False, indent=1))
    return path


def open_issue(date, groups, reason_text, text, log=print):
    """Задача в GitHub: распозналось сомнительно — пусть посмотрит человек."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "raspisanie-utgt/raspisanie-utgt.github.io")
    assignee = os.environ.get("HEALTH_ASSIGNEE") or None
    if not token:
        log("нет GITHUB_TOKEN — задачу не открыть")
        return None
    h = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    base = "https://api.github.com/repos/" + repo
    try:
        requests.post(base + "/labels", headers=h, json={"name": LABEL, "color": "2456c7"}, timeout=30)
    except Exception:
        pass
    body = ("Замена из беседы ВК на **%s** распозналась неуверенно — на сайте её нет.\n\n"
            "Причина: %s.\n"
            "Группы в распоряжении: %s.\n\n"
            "Распознанный текст:\n```\n%s\n```\n\n"
            "Посмотрите фото в беседе и поправьте data/zameny/%s.json или data/zameny_popravki.json."
            % (date, reason_text, ", ".join(groups) if groups else "не прочитались",
               _norm(text)[:1500], date))
    data = {"title": "Замена из ВК на %s: распознано сомнительно" % date,
            "body": body, "labels": [LABEL]}
    if assignee:
        data["assignees"] = [assignee]
    r = requests.post(base + "/issues", headers=h, json=data, timeout=30)
    r.raise_for_status()
    return r.json().get("number")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="ссылки на фото распоряжения из беседы ВК (через запятую)")
    ap.add_argument("--file", help="локальный файл — для проверки без ВК")
    ap.add_argument("--msg", default="", help="номер сообщения ВК — для отчёта")
    ap.add_argument("--dry", action="store_true", help="только показать, что получилось, ничего не писать")
    args = ap.parse_args()
    tmpdir = tempfile.mkdtemp(prefix="vkzam")
    try:
        if args.file:
            files = [Path(args.file)]
        else:
            files = []
            for i, u in enumerate([x for x in (args.url or "").split(",") if x.strip()][:MAX_PHOTOS], 1):
                p = Path(tmpdir) / ("photo%d.png" % i)
                download(u.strip(), p)
                files.append(p)
        if not files:
            print("нужен --url или --file")
            return 2
        res = publish(files, dry=args.dry)
    except Exception as e:
        res = {"status": "error", "error": str(e)[:300]}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    res["msg"] = args.msg
    print("итог: " + json.dumps(res, ensure_ascii=False))
    if res.get("status") in ("uncertain", "no_date", "error") and not args.dry:
        try:
            n = open_issue(res.get("date") or "?", res.get("groups") or [],
                           res.get("reason") or res.get("error") or res.get("status"),
                           res.get("text") or "")
            if n:
                res["issue"] = n
                print("открыта задача #" + str(n))
        except Exception as e:
            print("задачу не открыть: " + str(e))
        try:
            write_result(res)
        except Exception as e:
            print("результат не записать: " + str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
