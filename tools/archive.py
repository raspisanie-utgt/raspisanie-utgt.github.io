"""Вечный архив замен. На сайте замены хранятся 21 день, а здесь — все, начиная с 19.10.2026.

Текст: data/archive/ГГГГ-ММ.json.gz — {дата: замены всех групп}, сжатый.
Картинки распоряжений: data/archive/img/ГГГГ-ММ-ДД-N.png — 16 оттенков серого (в ~2 раза меньше).

    python tools/archive.py                      # обновить архив из data/zameny
    python tools/archive.py --show 11-А          # все замены группы
    python tools/archive.py --show 11-А --from 2026-11-01 --to 2026-11-30
    python tools/archive.py --show all --from 2026-10-27   # все группы
"""
import argparse
import gzip
import io
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ZAMENY = ROOT / "data" / "zameny"
ARCHIVE = ROOT / "data" / "archive"
FIELDS = ("title", "po_raspisaniyu", "ocr_ok", "ocr_uncertain", "fetched_at", "first_seen", "updated_at", "all_changes")


def record(meta):
    rec = {k: meta.get(k) for k in FIELDS}
    rec["images"] = [i["file"] for i in meta.get("images", [])]
    return rec


def read_month(path):
    if not path.exists():
        return {}
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def write_month(path, days):
    raw = json.dumps(dict(sorted(days.items())), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    # mtime=0 — одинаковые данные дают одинаковый файл, без лишних коммитов
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as f:
        f.write(raw)
    path.write_bytes(buf.getvalue())


def compress_image(src, dst):
    # JPEG не поддерживает режим P (16 оттенков). Сохраняем JPEG в RGB,
    # а PNG — в компактной палитре, сохраняя расширение из метаданных.
    with Image.open(src) as original:
        gray = original.convert("L").quantize(16)
        if dst.suffix.lower() in (".jpg", ".jpeg"):
            gray.convert("RGB").save(dst, format="JPEG", quality=78, optimize=True)
        else:
            gray.save(dst, format="PNG", optimize=True)


def update(zameny=ZAMENY, archive=ARCHIVE, log=print):
    """Переносит в архив все дни из data/zameny. Уже сохранённый день перезаписывается,
    если замены поменялись (например, техникум выложил исправленное распоряжение)."""
    (archive / "img").mkdir(parents=True, exist_ok=True)
    months = {}
    for p in sorted(zameny.glob("????-??-??.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        month = archive / f"{meta['date'][:7]}.json.gz"
        days = months.setdefault(month, read_month(month))
        rec = record(meta)
        old = days.get(meta["date"])
        if old and {k: v for k, v in old.items() if k != "fetched_at"} == \
                {k: v for k, v in rec.items() if k != "fetched_at"}:
            continue
        days[meta["date"]] = rec
        for name in rec["images"]:
            if (zameny / name).exists():
                compress_image(zameny / name, archive / "img" / name)
        log(f"архив: {meta['date']} {'обновлён' if old else 'добавлен'}")
    for month, days in months.items():
        new = dict(sorted(days.items()))
        if read_month(month) != new:
            write_month(month, new)


def load_all(archive=ARCHIVE):
    days = {}
    for p in sorted(archive.glob("????-??.json.gz")):
        days.update(read_month(p))
    return days


def show(group, date_from=None, date_to=None, archive=ARCHIVE):
    lines = []
    for date, rec in sorted(load_all(archive).items()):
        if (date_from and date < date_from) or (date_to and date > date_to):
            continue
        groups = rec["all_changes"] or {}
        rows = groups.items() if group == "all" else [(group, groups.get(group, []))]
        found = [(g, r) for g, rs in rows for r in rs]
        if rec["po_raspisaniyu"]:
            lines.append(f"{date}: занятия по расписанию")
            continue
        if not found:
            continue
        lines.append(f"{date}  {rec['title'] or ''}".rstrip())
        for g, r in found:
            les = "РоВ" if r["lessons"] == [0] else ("-".join(map(str, [r["lessons"][0], r["lessons"][-1]]))
                                                    if r["lessons"] else (r["time"] or "?"))
            lines.append(f"  {g:5} {les:6} {r['subject']}" + (f" — {r['room']}" if r["room"] else "")
                         + (" (?)" if r["uncertain"] else ""))
    return "\n".join(lines) or "в архиве ничего не найдено"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", metavar="ГРУППА", help="показать замены группы (или all)")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    args = ap.parse_args()
    if args.show:
        print(show(args.show, args.date_from, args.date_to))
    else:
        update()
    return 0


if __name__ == "__main__":
    sys.exit(main())
