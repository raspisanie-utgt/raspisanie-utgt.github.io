"""Собирает статический сайт в папку _site: site/* + data/* + status.json.

    python build_site.py                  # обычная сборка
    python build_site.py --scrape-failed  # отметить, что проверка замен упала
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def bust_cache(out):
    """app.js -> app.js?v=<хэш содержимого>: после обновления телефон не возьмёт старый скрипт из кэша."""
    def versioned(m):
        name = m.group(2)
        digest = hashlib.sha1((out / name).read_bytes()).hexdigest()[:8]
        return f'{m.group(1)}="{name}?v={digest}"'

    for page in out.glob("*.html"):
        html = page.read_text(encoding="utf-8")
        html = re.sub(r'(src|href)="([\w.-]+\.(?:js|css))"', versioned, html)
        page.write_text(html, encoding="utf-8")


def minify_json(data_dir):
    """JSON без отступов и пробелов — меньше качать и быстрее разбирать на слабом телефоне."""
    for p in data_dir.rglob("*.json"):
        p.write_text(json.dumps(json.loads(p.read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":")),
                     encoding="utf-8")


def webp_images(zameny_dir):
    """Картинки распоряжений ещё и в WebP без потерь — в 2–2,5 раза легче PNG, качество то же."""
    from PIL import Image
    for png in sorted(zameny_dir.glob("*.png")) + sorted(zameny_dir.glob("*.jpg")):
        with Image.open(png) as im:
            im.save(png.with_suffix(".webp"), "WEBP", lossless=True, method=4)


def minify_assets(out):
    """Скрипты и стили без комментариев и пробелов — на треть меньше качать.
    Без rjsmin/rcssmin (не установлены) — остаются как есть."""
    try:
        import rcssmin
        import rjsmin
    except ImportError:
        print("rjsmin/rcssmin не установлены — скрипты и стили без сжатия")
        return
    for f in out.glob("*.js"):
        f.write_text(rjsmin.jsmin(f.read_text(encoding="utf-8")), encoding="utf-8")
    for f in out.glob("*.css"):
        f.write_text(rcssmin.cssmin(f.read_text(encoding="utf-8")), encoding="utf-8")


def inline_preload(out):
    """В index.html — какие файлы у групп и на какие дни есть замены: страница начинает грузить их сразу."""
    groups = json.loads((out / "data" / "groups" / "index.json").read_text(encoding="utf-8"))["groups"]
    days = json.loads((out / "data" / "zameny" / "index.json").read_text(encoding="utf-8"))["days"]
    files = {g["group"]: g["file"] for g in groups}
    page = out / "index.html"
    html = page.read_text(encoding="utf-8")
    html = html.replace("__GROUP_FILES__", json.dumps(files, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__ZAMENY_DAYS__", json.dumps(days[-14:], separators=(",", ":")))
    page.write_text(html, encoding="utf-8")


def write_history(out_dir):
    """История замен из вечного архива (data/archive) -> data/history/all.json: все распоряжения
    по дням, от новых к старым, по всем группам; картинки — сжатые копии из архива."""
    import gzip
    days = {}
    for p in sorted((ROOT / "data" / "archive").glob("????-??.json.gz")):
        days.update(json.loads(gzip.decompress(p.read_bytes()).decode("utf-8")))
    out_dir.mkdir(parents=True, exist_ok=True)
    hist = []
    for date in sorted(days, reverse=True):
        d = days[date]
        groups = {g: [{k: r.get(k) for k in ("lessons", "time", "subject", "room", "uncertain")} for r in rows]
                  for g, rows in (d.get("all_changes") or {}).items() if rows}
        hist.append({"date": date, "title": d.get("title") or "", "po_raspisaniyu": bool(d.get("po_raspisaniyu")),
                     "images": d.get("images") or [], "groups": groups})
    (out_dir / "all.json").write_text(json.dumps({"days": hist}, ensure_ascii=False, separators=(",", ":")),
                                      encoding="utf-8")
    img = ROOT / "data" / "archive" / "img"
    if img.exists():
        shutil.copytree(img, out_dir / "img", dirs_exist_ok=True)


def build(out=ROOT / "_site", scrape_ok=True):
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    # расписания всех групп: на сайте 11-А нужны для «где сейчас преподаватель»
    # архив замен сайту не нужен — он для запросов «что было тогда-то»
    shutil.copytree(ROOT / "data", out / "data", ignore=shutil.ignore_patterns("archive"))
    zameny = out / "data" / "zameny"
    zameny.mkdir(exist_ok=True)
    if not (zameny / "index.json").exists():
        (zameny / "index.json").write_text('{"days": []}', encoding="utf-8")
    write_history(out / "data" / "history")
    minify_json(out / "data")
    webp_images(out / "data" / "zameny")
    inline_preload(out)
    minify_assets(out)
    # змейка грузится из app.js по требованию — версия её файла вписывается туда же (до хэша самого app.js)
    snake = hashlib.sha1((out / "snake.js").read_bytes()).hexdigest()[:8]
    app = out / "app.js"
    app.write_text(app.read_text(encoding="utf-8").replace("SNAKE_V", '"' + snake + '"'), encoding="utf-8")
    bust_cache(out)
    # версия кэша для работы без интернета: меняется только при изменении самого сайта (site/),
    # а не данных каждый час — иначе телефон при каждом заходе заново скачивал бы в фоне всё целиком
    # (данные и так берутся из сети и сохраняются при каждом открытии)
    digest = hashlib.sha1()
    for f in sorted((ROOT / "site").rglob("*")):
        if f.is_file() and f.name != "sw.js":
            digest.update(f.name.encode()); digest.update(f.read_bytes())
    digest.update((ROOT / "site" / "sw.js").read_bytes())
    sw = out / "sw.js"
    sw.write_text(sw.read_text(encoding="utf-8").replace("__BUILD__", digest.hexdigest()[:10]), encoding="utf-8")
    status = {"checked_at": dt.datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="minutes"),
              "ok": scrape_ok}
    (out / "status.json").write_text(json.dumps(status), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scrape-failed", action="store_true")
    args = ap.parse_args()
    print("собрано в", build(scrape_ok=not args.scrape_failed))
