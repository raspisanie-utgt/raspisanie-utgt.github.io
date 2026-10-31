"""Проверка распознавания на нарисованных таблицах «как распоряжение о замене»: случайные группы, уроки
(«8-30», «14-50», «3-6»…), длинные названия в две строки, кабинеты; три размера, как у настоящих картинок
(533, 620, 860 точек), шрифт как Times (Liberation Serif), чётко / уменьшено / чуть размыто.
Считает, где распознавание ошиблось и пометило ли строку «неуверенно» (без пометки — плохо).

    python tools/ocr_sintetika.py            # 36 таблиц (~5 минут на 4 ядрах)
    python tools/ocr_sintetika.py 90 --seed 7
"""
import argparse
import json
import multiprocessing as mp
import os
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import scraper  # noqa: E402

FONTS = "/usr/share/fonts/truetype/liberation/LiberationSerif-{}.ttf"
# ширина картинки -> (границы столбцов, высота строки, размер шрифта) — сняты с настоящих распоряжений
SIZES = {533: ([37, 89, 129, 446, 505], 12, 11), 620: ([43, 103, 149, 513, 581], 14, 12.5),
         860: ([63, 147, 210, 710, 804], 19, 16.5)}
LESSONS = ["1-2", "3-4", "5-6", "7-8"] * 4 + ["9-10"] * 2 + ["1-4", "5-8", "3-6", "1-8", "8-30", "8-30", "8-30",
                                                             "14-50", "12-40", "3", "5"]
DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]


def make_rows(rnd, vocab, rooms):
    out = []
    for g in sorted(rnd.sample(scraper.KNOWN_GROUPS, rnd.randint(4, 12)), key=scraper.KNOWN_GROUPS.index):
        for k in range(rnd.choice([1, 1, 1, 2, 2, 3])):
            les = rnd.choice(LESSONS)
            subj = rnd.choice(["Разговоры о важном", scraper.CANCEL]) if les == "8-30" else \
                scraper.CANCEL if rnd.random() < 0.45 else rnd.choice(vocab)
            room = "" if subj == scraper.CANCEL else ("Акт.зал" if rnd.random() < 0.05 else rnd.choice(rooms + [""] * 5))
            out.append({"group": g if k == 0 else "", "lessons": les, "subject": subj, "room": room})
    return out


def render(rows, width, rnd, k):
    vl, rh, fs = SIZES[width]
    f, fb = ImageFont.truetype(FONTS.format("Regular"), fs * k), ImageFont.truetype(FONTS.format("Bold"), fs * k)
    probe = ImageDraw.Draw(Image.new("L", (10, 10)))

    def wrap(text):
        lines = [""]
        for w in text.split():
            t = (lines[-1] + " " + w).strip()
            if probe.textlength(t, font=f) <= (vl[3] - vl[2] - 6) * k or not lines[-1]:
                lines[-1] = t
            else:
                lines.append(w)
        return lines
    lay = [(r, wrap(r["subject"])) for r in rows]
    top = 300 if width == 860 else 230
    height = top + rh * 2 + sum(rh * len(ls) for _, ls in lay) + 40
    im = Image.new("L", (width * k, height * k), 255)
    d = ImageDraw.Draw(im)
    for i, t in enumerate(["ФЕДЕРАЛЬНОЕ АГЕНТСТВО ЖЕЛЕЗНОДОРОЖНОГО ТРАНСПОРТА", "УТЖТ - филиал ПГУПС", "РАСПОРЯЖЕНИЕ"]):
        d.text((width * k // 2, (30 + i * 35) * k), t, font=fb, fill=0, anchor="mm")
    x0, x1, y = vl[0] * k, vl[-1] * k, top * k

    def line(y):
        d.line([(x0, y), (x1, y)], fill=0, width=k)
    line(y)
    d.text(((x0 + x1) // 2, y + rh * k // 2), f"{rnd.choice(DAYS)}, {rnd.choice([1, 2])}-я неделя", font=fb, fill=0, anchor="mm")
    y += rh * k
    line(y)
    for (a, b), t in zip(zip(vl, vl[1:]), ["группа", "урок", "наименование дисциплины", "аудитория"]):
        d.text(((a + b) * k // 2, y + rh * k // 2), t, font=fb, fill=0, anchor="mm")
    y += rh * k
    line(y)
    for r, ls in lay:
        h, cy = rh * len(ls) * k, y + rh * len(ls) * k // 2
        if r["group"]:
            d.text(((vl[0] + vl[1]) * k // 2, cy), r["group"], font=f, fill=0, anchor="mm")
        d.text(((vl[1] + vl[2]) * k // 2, cy), r["lessons"], font=f, fill=0, anchor="mm")
        for j, t in enumerate(ls):
            d.text(((vl[2] + 3) * k, y + (j * rh + rh // 2) * k), t, font=f, fill=0, anchor="lm")
        if r["room"]:
            d.text(((vl[3] + vl[4]) * k // 2, cy), r["room"], font=f, fill=0, anchor="mm")
        y += h
        line(y)
    for x in vl:
        d.line([(x * k, top * k + (0 if x in (vl[0], vl[-1]) else rh * k)), (x * k, y)], fill=0, width=k)
    if k > 1:
        im = im.resize((width, height), Image.LANCZOS if k == 3 else Image.BILINEAR)
    if k == 2:
        im = im.filter(ImageFilter.GaussianBlur(0.45))
    return im


def check(task):
    path, rows = task
    t = scraper.ocr_table(path, scraper.subject_vocab())
    for r in t["rows"]:  # без расписания: расхождение прочтений кабинета сразу неуверенно
        if len(r.pop("room_alts", None) or []) > 1:
            r["uncertain"] = True
    out, g = [], None
    if len(t["rows"]) != len(rows):
        return [("таблица", f"строк {len(rows)}", f"распознано {len(t['rows'])}", False)]
    for want, r in zip(rows, t["rows"]):
        g = want["group"] or g
        w = {"группа": g, "урок": scraper.parse_lessons(want["lessons"]), "кабинет": want["room"].replace("Акт.зал", "1-34"),
             "предмет": want["subject"]}
        got = {"группа": r["group"], "урок": (r["lessons"], r["time"]), "кабинет": r["room"], "предмет": r["subject"]}
        bad = [k for k in w if w[k] != got[k]]
        out += [(k, str(w[k])[:40], str(got[k])[:40], r["uncertain"]) for k in bad]
        if not bad and r["uncertain"]:
            out.append(("лишняя тревога", "", "", True))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=36)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # иначе 4 процесса tesseract по 4 потока душат процессор
    vocab, rooms = scraper.subject_vocab(), sorted(r for r in scraper.known_rooms() if r != "?")
    tmp = Path(tempfile.mkdtemp(prefix="ocr_sint_"))
    tasks = []
    for i in range(a.n):
        rnd = random.Random(a.seed * 100000 + i)
        rows = make_rows(rnd, vocab, rooms)
        p = tmp / f"t{i:03d}.png"
        render(rows, [533, 620, 860][i % 3], rnd, [1, 3, 2][i // 3 % 3]).save(p)
        tasks.append((str(p), rows))
    with mp.Pool(os.cpu_count()) as pool:
        res = [x for part in pool.map(check, tasks) for x in part]
    rows = sum(len(r) for _, r in tasks)
    errors = [x for x in res if x[0] != "лишняя тревога"]
    silent = [x for x in errors if not x[3]]
    print(f"таблиц {a.n}, строк {rows}: ошибок {len(errors)} {dict(Counter(x[0] for x in errors))}, "
          f"из них без пометки «неуверенно» {len(silent)}, лишних тревог {len(res) - len(errors)}")
    for x in silent:
        print("   БЕЗ ПОМЕТКИ:", x[:3])
    print("картинки:", tmp)
    return 1 if silent else 0


if __name__ == "__main__":
    sys.exit(main())
