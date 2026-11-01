"""Новый семестр и новый учебный год — без человека.

Раз в час (update.yml, до tools/sources.py) смотрит PDF на странице «Расписания и графики» техникума:

- появилось расписание нового семестра — разбирает (tools/extract_schedule.py), проверяет и откладывает в
  data/next/; в data/groups/ оно переходит само в каникулы перед началом семестра (switch_on), чтобы сайт
  заранее показывал новые пары, но не ставил их на последние учебные дни старого семестра;
- поменялся PDF текущего расписания — разбирает и выкладывает сразу (группы, у которых пары не изменились,
  остаются «сверенными»);
- появился учебный график нового учебного года — разбирает и добавляет к data/calendar.json (старый год
  остаётся до 31 августа), поменялся график этого года — заменяет.

Не прошло проверку (мало групп, пустые группы, ошибки в данных, праздники не на своих днях) — ничего не меняет,
сайт работает по-старому. Обо всём — заметка в data/notices.txt; tools/sources.py откроет по ней задачу.

    python tools/semestr.py          # проверить и сделать, что нужно; состояние — data/semestr.json
"""
import collections
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_data  # noqa: E402
import extract_calendar  # noqa: E402
import extract_schedule  # noqa: E402
import sources  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHED_RE = re.compile(r"raspisanie.*semestr", re.I)
KUG_RE = re.compile(r"kug.*ocn", re.I)
FIXED = ["11-04", "02-23", "03-08", "05-01", "05-09", "06-12"]  # праздники, которые не переносятся с даты
SWITCH_MAX_DAYS = 21  # новое расписание появляется на сайте самое раннее за 3 недели до начала семестра


def today_msk():
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)).date()


def load(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def notice(text, data_dir):
    p = data_dir / "notices.txt"
    p.write_text((p.read_text(encoding="utf-8") if p.exists() else "") + text.strip() + "\n\n", encoding="utf-8")


def iso(d):
    return d.isoformat()


# ---------- учебный график: каникулы и выходные ----------

def winter_break(cal, year):
    """Самые частые у групп зимние каникулы учебного года year (с декабря year по январь year+1): (from, to) или None."""
    c = collections.Counter((p["from"], p["to"]) for g in cal.get("groups", {}).values() for p in g.get("periods", [])
                            if p["type"] == "kanikuly" and f"{year}-12-01" <= p["from"] <= f"{year + 1}-01-31")
    return c.most_common(1)[0][0] if c else None


def day_off_share(cal, date):
    """Доля групп, у которых в этот день нет занятий (воскресенье, праздник, каникулы, практика…)."""
    d = iso(date)
    if date.isoweekday() == 7 or any(h["date"] == d for h in cal.get("holidays", [])):
        return 1.0
    groups = cal.get("groups", {})
    if not groups:
        return 0.0
    # нет занятий: каникулы, практика и т. п.; у выпускников после последнего периода (экзамены сданы) — тоже
    off = sum(any(p.get("no_classes") and p["from"] <= d <= p["to"] for p in g.get("periods", [])) or
              bool(g.get("periods")) and all(p["to"] < d for p in g["periods"]) for g in groups.values())
    return off / len(groups)


def switch_on(valid_from, cal, today):
    """Когда переложить новое расписание в data/groups: в начале выходных перед семестром (не раньше чем за 3 недели),
    чтобы на сайте заранее были видны новые пары, а последние учебные дни старого семестра остались со старыми."""
    start = dt.date.fromisoformat(valid_from)
    if start <= today:
        return today
    d = start
    while (start - d).days < SWITCH_MAX_DAYS and d - dt.timedelta(days=1) > today and \
            day_off_share(cal, d - dt.timedelta(days=1)) >= 0.8:
        d -= dt.timedelta(days=1)
    return d


def semester_dates(info, cal, cur_index):
    """С какого и по какой день действует расписание; третье — True, если конец угадан (графика ещё нет)."""
    y1 = int(info["year"][:4])
    if info["semester"] == 1:
        wb = winter_break(cal, y1)
        return f"{y1}-09-01", (wb[1] if wb else f"{y1 + 1}-01-11"), not wb
    wb = winter_break(cal, y1)
    if wb:
        start = iso(dt.date.fromisoformat(wb[1]) + dt.timedelta(days=1))
    elif cur_index.get("year") == info["year"] and cur_index.get("valid_to"):
        start = iso(dt.date.fromisoformat(cur_index["valid_to"]) + dt.timedelta(days=1))
    else:
        start = f"{y1 + 1}-01-12"
    return start, f"{y1 + 1}-08-31", False


# ---------- проверки ----------

def check_schedule(out_dir, old_index):
    """Что не так с разобранным расписанием (пусто — всё хорошо)."""
    index = load(out_dir / "index.json", {})
    groups = {g["group"]: load(out_dir / g["file"]) for g in index.get("groups", [])}
    problems = []
    old_n = len(old_index.get("groups", []))
    if len(groups) < max(12, int(old_n * 0.7)):
        problems.append(f"нашлось только {len(groups)} групп (было {old_n})")
    for g, s in groups.items():
        days = [d for d, es in s["days"].items() if es]
        pairs = sum(len(es) for es in s["days"].values())
        if pairs < 8 or len(days) < 3:
            problems.append(f"{g}: всего {pairs} пар в {len(days)} днях — похоже, не разобралось")
    warns = sum(len(s.get("warnings", [])) for s in groups.values())
    if warns > 2 * max(1, len(groups)):
        problems.append(f"много сомнительных мест при разборе: {warns}")
    staff_file = DATA / "teachers.json"
    staff = set(load(staff_file, {}).get("by_short", [])) if staff_file.exists() else set()
    if groups:
        errors, _, _ = check_data.check_schedules(groups, staff)
        problems += [f"ошибка в данных: {e}" for e in errors[:10]]
    return problems


def check_calendar(cal, year):
    """Что не так с разобранным графиком: праздники должны встать на свои даты — это проверяет, что дни
    недели в графике поняты правильно."""
    problems = []
    if len(cal.get("groups", {})) < 12:
        problems.append(f"нашлось только {len(cal.get('groups', {}))} групп")
    dates = {h["date"] for h in cal.get("holidays", [])}
    expect = []
    for md in FIXED:
        y = year if md >= "09" else year + 1
        d = dt.date.fromisoformat(f"{y}-{md}")
        if d.isoweekday() != 7:
            expect.append(iso(d))
    found = [d for d in expect if d in dates]
    if len(found) < max(1, len(expect) - 2):
        problems.append(f"праздники не на своих днях: в графике {sorted(dates)}, ждали {expect}")
    if any(dt.date.fromisoformat(d).isoweekday() == 7 for d in dates):
        problems.append("выходной-праздник выпал на воскресенье — дни недели поняты неверно")
    if not winter_break(cal, year):
        problems.append("не нашлось зимних каникул")
    empty = [g for g, v in cal.get("groups", {}).items() if not v.get("periods")]
    if len(empty) > len(cal.get("groups", {})) / 3:
        problems.append(f"у многих групп нет ни одного периода: {', '.join(empty)}")
    return problems


def calendar_year(cal):
    m = re.search(r"(20\d\d)\s*-\s*20\d\d", cal.get("title", ""))
    return int(m.group(1)) if m else None


def merge_calendars(old, new, year):
    """Старый год — до 31 августа, новый — с 1 сентября; специальности и курсовые — нового года."""
    start = f"{year}-09-01"
    out = {k: v for k, v in new.items() if k not in ("holidays", "groups")}
    out["holidays"] = [h for h in old.get("holidays", []) if h["date"] < start] + new.get("holidays", [])
    out["groups"] = {}
    for g in sorted(set(old.get("groups", {})) | set(new.get("groups", {}))):
        o, n = old.get("groups", {}).get(g, {}), new.get("groups", {}).get(g)
        base = dict(n or o)
        base["periods"] = [p for p in o.get("periods", []) if p["from"] < start] + (n or {}).get("periods", [])
        out["groups"][g] = base
    return out


# ---------- раскладка файлов ----------

def install(src_dir, groups_dir):
    """Переложить разобранное расписание в groups_dir (файлы групп + index.json), лишние файлы групп убрать."""
    groups_dir.mkdir(parents=True, exist_ok=True)
    index = load(src_dir / "index.json")
    keep = {g["file"] for g in index["groups"]} | {"index.json"}
    for g in index["groups"]:
        shutil.copyfile(src_dir / g["file"], groups_dir / g["file"])
    for f in groups_dir.glob("*.json"):
        if f.name not in keep:
            f.unlink()
    save(groups_dir / "index.json", {k: v for k, v in index.items() if k != "switch_on"})


def maybe_switch(data_dir, today, log=print):
    """Пора — отложенное расписание нового семестра становится текущим."""
    nxt = data_dir / "next"
    index = load(nxt / "index.json")
    if not index or index.get("switch_on", "9999") > iso(today):
        return False
    # нумерацию недель за это время мог поправить scraper.py (fix_week_anchor) — берём текущую
    cur = load(data_dir / "groups" / "index.json", {})
    first = (cur.get("groups") or [{}])[0].get("file")
    anchor = first and load(data_dir / "groups" / first, {}).get("week_anchor")
    if anchor:
        for g in index["groups"]:
            f = load(nxt / g["file"])
            f["week_anchor"] = anchor
            save(nxt / g["file"], f)
    install(nxt, data_dir / "groups")
    shutil.rmtree(nxt)
    log(f"расписание {index.get('semester')} семестра {index.get('year')} стало текущим")
    notice(f"Расписание {index.get('semester')} семестра {index.get('year')} включено на сайте "
           f"(действует с {index['valid_from']}). Оно разобрано из PDF автоматически — сверить с PDF: {index['source']}",
           data_dir)
    return True


def changed_groups(new_dir, old_dir):
    """Группы, у которых пары не такие, как были."""
    old = {g["group"]: load(old_dir / g["file"]) for g in load(old_dir / "index.json", {}).get("groups", [])}
    out = []
    for g in load(new_dir / "index.json")["groups"]:
        o = old.get(g["group"])
        if not o or o["days"] != load(new_dir / g["file"])["days"]:
            out.append(g["group"])
    return out


# ---------- разбор одного PDF ----------

def download(url, folder):
    r = requests.get(url, timeout=120, headers=sources.UA)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise ValueError("по ссылке не PDF")
    path = Path(folder) / "file.pdf"
    path.write_bytes(r.content)
    return path


def do_schedule(url, pdf, data_dir, today, log=print):
    info = extract_schedule.pdf_info(pdf)
    if not info:
        return f"не понял по заголовку, какой это семестр — {url}"
    cur = load(data_dir / "groups" / "index.json", {})
    nxt = load(data_dir / "next" / "index.json", {})
    key = (info["year"], info["semester"])
    cur_key = (cur.get("year", ""), cur.get("semester", 0))
    if key < cur_key or (nxt and key < (nxt["year"], nxt["semester"])):
        log(f"{url}: старое расписание ({info['semester']} семестр {info['year']}) — пропускаю")
        return None
    cal = load(data_dir / "calendar.json", {})
    same = key == cur_key
    if same:
        valid_from, valid_to, guessed = cur.get("valid_from"), cur.get("valid_to"), cur.get("valid_to_guess", False)
    else:
        valid_from, valid_to, guessed = semester_dates(info, cal, cur)
    first = (cur.get("groups") or [{}])[0].get("file")
    anchor = (load(data_dir / "groups" / first, {}) if first else {}).get("week_anchor") or extract_schedule.WEEK_ANCHOR
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "groups"
        extract_schedule.extract_all(pdf, out, url, valid_from, valid_to, info["title"], anchor, verified=(),
                                     info=info, log=lambda *a: None)
        problems = check_schedule(out, cur)
        if problems:
            return (f"Нашлось расписание {info['semester']} семестра {info['year']}, но разобрать его надёжно не вышло — "
                    f"сайт работает по-старому. Что не так:\n" + "\n".join("- " + p for p in problems) +
                    f"\nPDF: {url}. Разобрать вручную: `python tools/extract_schedule.py <pdf>`.")
        index = load(out / "index.json")
        if guessed:
            index["valid_to_guess"] = True
        if same:
            # поменялся PDF этого же семестра — сразу; сверенные человеком группы с теми же парами остаются сверенными
            changed = changed_groups(out, data_dir / "groups")
            was = {g["group"] for g in cur.get("groups", []) if g.get("verified")}
            for g in index["groups"]:
                if g["group"] in was and g["group"] not in changed:
                    g["verified"] = True
                    f = load(out / g["file"])
                    f["verified"] = True
                    save(out / g["file"], f)
            save(out / "index.json", index)
            if not changed and cur.get("source") == url:
                return None
            install(out, data_dir / "groups")
            return (f"Расписание {info['semester']} семестра {info['year']} на сайте техникума поменялось — сайт разобрал "
                    f"и выложил новое. Изменились группы: {', '.join(changed) or 'нет (только файл)'} — сверить их с PDF: {url}")
        index["switch_on"] = iso(switch_on(valid_from, cal, today))
        save(out / "index.json", index)
        if index["switch_on"] <= iso(today):
            install(out, data_dir / "groups")
            shutil.rmtree(data_dir / "next", ignore_errors=True)
            when = "включено на сайте сразу"
        else:
            shutil.rmtree(data_dir / "next", ignore_errors=True)
            shutil.copytree(out, data_dir / "next")
            when = f"появится на сайте {index['switch_on']} (до начала семестра — каникулы)"
    return (f"Нашлось расписание {info['semester']} семестра {info['year']} — разобрано автоматически и {when}; "
            f"действует с {valid_from} по {valid_to}" + (" (конец угадан: учебного графика на этот год ещё нет)" if guessed else "") +
            f". Сверить с PDF: {url}. Ручные поправки к прошлому расписанию (data/popravki.json) к нему не применялись.")


def do_calendar(url, pdf, data_dir, log=print):
    year = extract_calendar.pdf_year(pdf)
    if not year:
        return f"не понял по заголовку, на какой учебный год график — {url}"
    path = data_dir / "calendar.json"
    old = load(path, {})
    old_year = calendar_year(old) or 0
    if year < old_year:
        log(f"{url}: старый график ({year}) — пропускаю")
        return None
    saved = extract_calendar.YEAR_START, extract_calendar.DAYS, extract_calendar.SOURCE
    extract_calendar.configure(year, url)
    try:
        new = extract_calendar.extract(pdf)
    except Exception as e:  # noqa: BLE001 — вёрстка графика поменялась: сайт работает по-старому
        return f"Нашёлся учебный график на {year}/{year + 1}, но разобрать не вышло ({e}) — сайт работает по-старому. PDF: {url}"
    finally:
        extract_calendar.YEAR_START, extract_calendar.DAYS, extract_calendar.SOURCE = saved
    problems = check_calendar(new, year)
    if problems:
        return (f"Нашёлся учебный график на {year}/{year + 1}, но разобрать его надёжно не вышло — сайт работает "
                f"по-старому. Что не так:\n" + "\n".join("- " + p for p in problems) + f"\nPDF: {url}")
    # прошлый год (до 1 сентября) остаётся и при замене графика этого года: летом в файле их два
    merged = merge_calendars(old, new, year)
    if year == old_year:
        if json.dumps(merged, sort_keys=True) == json.dumps(old, sort_keys=True):
            return None
        save(path, merged)
        fix_guessed_end(data_dir, new)
        return f"Учебный график на {year}/{year + 1} на сайте техникума поменялся — сайт разобрал и выложил новый. PDF: {url}"
    save(path, merged)
    fix_guessed_end(data_dir, new)
    return f"Нашёлся учебный график на {year}/{year + 1} — разобран автоматически и добавлен на сайт. Сверить с PDF: {url}"


def fix_guessed_end(data_dir, cal):
    """Расписание 1 семестра пришло раньше графика и конец семестра был угадан — теперь берём из графика."""
    for idx in (data_dir / "groups" / "index.json", data_dir / "next" / "index.json"):
        index = load(idx)
        if not index or not index.get("valid_to_guess") or index.get("semester") != 1:
            continue
        wb = winter_break(cal, int(index["year"][:4]))
        if wb:
            index["valid_to"] = wb[1]
            index.pop("valid_to_guess")
            save(idx, index)


# ---------- главное ----------

def candidates(data_dir):
    """Адреса PDF расписания и графика: со страницы техникума и те, что сейчас на сайте."""
    urls = set(sources.page_pdfs())
    urls.add(load(data_dir / "groups" / "index.json", {}).get("source", ""))
    urls.add(load(data_dir / "calendar.json", {}).get("source", ""))
    cal = sorted(u for u in urls if KUG_RE.search(u))
    sched = sorted(u for u in urls if SCHED_RE.search(u))
    return cal + sched  # график раньше: по нему считаются даты семестра


def main(data_dir=DATA, today=None):
    today = today or today_msk()
    state_path = data_dir / "semestr.json"
    state = load(state_path, {"tried": {}})
    maybe_switch(data_dir, today)
    current = {load(data_dir / "groups" / "index.json", {}).get("source"), load(data_dir / "calendar.json", {}).get("source")}
    for url in candidates(data_dir):
        fp = sources.fingerprint(url)
        if "status" in fp:
            print(f"{url}: сайт техникума ответил {fp['status']} — в следующий раз")
            continue
        prev = state["tried"].get(url)
        if prev == fp:
            continue
        if prev is None and url in current:
            state["tried"][url] = fp  # первая проверка: это то, из чего сайт уже собран
            continue
        print(f"разбираю {url}")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pdf = download(url, tmp)
                fp["sha1"] = hashlib.sha1(pdf.read_bytes()).hexdigest()
                if prev and prev.get("sha1") == fp["sha1"]:
                    state["tried"][url] = fp
                    continue
                text = do_calendar(url, pdf, data_dir) if KUG_RE.search(url) else do_schedule(url, pdf, data_dir, today)
        except Exception as e:  # noqa: BLE001 — один плохой PDF не мешает остальным; попробуем снова в следующий час
            print(f"{url}: не вышло — {e}")
            continue
        state["tried"][url] = fp
        if text:
            print(text)
            notice(text, data_dir)
    save(state_path, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
