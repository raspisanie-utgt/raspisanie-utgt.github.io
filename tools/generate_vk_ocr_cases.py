"""Generate labelled, offline test photos. Never write to the site's data directory."""
import argparse
import datetime as dt
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

WEEKDAYS = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
SUBJECTS = ("Математика", "Биология", "История России", "Физическая культура",
            "Электротехника и электроника", "Иностранный язык в профессиональной деятельности (английский)",
            "МДК.02.01 Строительство и реконструкция железных дорог")
GROUPS = ("11-А", "11-В", "11-Д", "11-Л", "11-П", "11-С", "21-А", "21-Л",
          "21-П", "21-С", "31-А", "31-Д", "31-П", "31-С", "41-А", "41-П", "41-С")
ROOMS = ("1-14", "1-30", "1-32", "2-7", "2-13", "2-15")


def make_rows(rng, size, style):
    rows = []
    for group in rng.sample(GROUPS, len(GROUPS)):
        pairs = sorted(rng.sample(range(5), min(size - len(rows), rng.randint(2, 5))))
        for offset, pair in enumerate(pairs):
            first = pair * 2 + 1
            subject = "Отменить" if rng.randrange(7) == 0 else rng.choice(SUBJECTS)
            room = "" if subject == "Отменить" or rng.randrange(8) == 0 else rng.choice(ROOMS)
            rows.append(dict(group=group, lessons=[first, first + 1], time=None, subject=subject,
                             room=room, label=offset == 0, style=style))
        if len(rows) == size:
            break
    return rows


def wrap(text, font, width):
    lines = [""]
    for word in text.split():
        candidate = (lines[-1] + " " + word).strip()
        if lines[-1] and font.getlength(candidate) > width:
            lines.append(word)
        else:
            lines[-1] = candidate
    return lines


def render(rows, signed, date, number, page, pages, font_path, profile, rng):
    font = ImageFont.truetype(str(font_path), 19)
    small = ImageFont.truetype(str(font_path), 16)
    xs = (25, 150, 245, 860, 995)
    wrapped = [wrap(row["subject"], font, xs[3] - xs[2] - 14) for row in rows]
    heights = [max(28, 22 * len(lines) + 8) for lines in wrapped]
    y = 215
    image = Image.new("L", (1020, y + sum(heights) + 42), 255)
    draw = ImageDraw.Draw(image)
    draw.text((25, 19), f"ТЕСТОВОЕ РАСПОРЯЖЕНИЕ № {number} — НЕ ДЛЯ ПУБЛИКАЦИИ", font=font, fill=12)
    draw.text((25, 62), f"Подписано {signed:%d.%m.%Y}   Лист {page} из {pages}", font=font, fill=12)
    draw.text((25, 113), f"Внести изменения в расписание учебных занятий на {date:%d.%m.%Y} года", font=font, fill=12)
    week = 2 if ((date - dt.date(2026, 11, 9)).days // 7) % 2 == 0 else 1
    draw.text((390, 158), f"{WEEKDAYS[date.weekday()]}, {week}-я неделя", font=font, fill=12)
    draw.line((xs[0], 151, xs[-1], 151), fill=10, width=2)
    draw.line((xs[0], 184, xs[-1], 184), fill=10, width=2)
    for x, label in zip(xs, ("группа", "урок", "наименование дисциплины", "аудитория")):
        draw.text((x + 8, 189), label, font=font, fill=12)
    bottom = y + sum(heights)
    for index, x in enumerate(xs):
        draw.line((x, 151 if index in (0, 4) else 184, x, bottom), fill=10, width=2)
    for index, (row, lines, height) in enumerate(zip(rows, wrapped, heights)):
        new_group = index == 0 or rows[index - 1]["group"] != row["group"]
        visible_group = new_group or row["style"] == "explicit"
        start = xs[0] if new_group or row["style"] != "merged" else xs[1]
        draw.line((start, y, xs[-1], y), fill=10, width=2)
        if visible_group:
            group_y = y + 5
            if row["style"] == "merged":
                end = index + 1
                while end < len(rows) and rows[end]["group"] == row["group"]:
                    end += 1
                group_y = y + (sum(heights[index:end]) - 20) // 2
            draw.text((xs[0] + 20, group_y), row["group"], font=font, fill=10)
        draw.text((xs[1] + 13, y + 5), f"{row['lessons'][0]}-{row['lessons'][-1]}", font=font, fill=10)
        for line_number, line in enumerate(lines):
            draw.text((xs[2] + 7, y + 4 + line_number * 22), line, font=font, fill=10)
        draw.text((xs[3] + 26, y + 5), row["room"], font=font, fill=10)
        y += height
    draw.line((xs[0], bottom, xs[-1], bottom), fill=10, width=2)
    draw.text((25, bottom + 10), "ТЕСТОВЫЕ ДАННЫЕ", font=small, fill=60)
    if profile in ("shadow", "severe"):
        shade = np.linspace(0, rng.randint(55, 103), image.width)
        pixels = np.asarray(image, dtype=float)
        image = Image.fromarray(np.clip(pixels - shade, 0, 255).astype(np.uint8))
    if profile in ("tilt", "severe"):
        image = image.rotate(rng.choice((-1, 1)) * rng.uniform(.45, 2.6),
                             Image.Resampling.BICUBIC, fillcolor=235)
    if profile in ("blur", "severe"):
        image = image.filter(ImageFilter.GaussianBlur(rng.uniform(.45, 1.25)))
    if profile in ("low", "severe"):
        scale = rng.uniform(.45, .68)
        image = image.resize((round(image.width * scale), round(image.height * scale)),
                             Image.Resampling.LANCZOS)
    return image


def stress_rows(number, style):
    """Контрольные примеры практик, длинных названий и последовательных отмен."""
    rows = [dict(group='11-Д', lessons=[first, first + 1], time=None, subject='Отменить', room='',
                 label=first == 1, style=style) for first in (1, 3, 5)]
    rows += [dict(group='31-А', lessons=list(range(1, 7)), time=None, subject='Учебная практика',
                  room='1-10', label=True, style=style),
             dict(group='41-А', lessons=list(range(5, 11)), time=None,
                  subject='МДК.01.03 Теоретические основы построения и эксплуатации микропроцессорных и диагностических систем автоматики',
                  canonical_subject='МДК.01.03 Теоретические основы построения и эксплуатации микропроц. и диагност. систем автоматики',
                  room='1-9', label=True, style=style)]
    if number % 5 == 0:
        rows.append(dict(group='11-А', lessons=[7, 8], time=None, subject='Несуществующая дисциплина XYZ',
                         room='1-14', label=True, style=style))
    return rows


def generate(output, font, count, stress=False):
    output.mkdir(parents=True, exist_ok=True)
    marker = output / "SYNTHETIC_ONLY"
    if not marker.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty or an existing synthetic corpus")
    marker.write_text("TEST DATA. DO NOT PUBLISH.\n", encoding="utf-8")
    with (output / "manifest.jsonl").open("w", encoding="utf-8") as manifest:
        for number in range(count):
            split = "train" if number < count * 7 // 10 else "holdout"
            rng = random.Random((432100 if split == "train" else 961800) + number)
            date = (dt.date(2026, 11, 19) if stress else
                    dt.date(2026, 10 + (number % 3), 1) + dt.timedelta(days=number % 4))
            signed = date - dt.timedelta(days=rng.randint(2, 8))
            style = rng.choice(("merged", "blank", "explicit"))
            profile = ("clean", "tilt", "blur", "shadow", "low", "jpeg", "severe")[number % 7]
            size = 10 + number % 41
            rows = stress_rows(number, style) if stress else make_rows(rng, size, style)
            size = len(rows)
            # Keep a page break in the middle of some groups. A repeated label starts each page.
            cut = rng.randint(size // 3, size * 2 // 3)
            parts = [rows[:cut], rows[cut:]] if number % 5 == 0 else [rows]
            folder = output / split
            folder.mkdir(exist_ok=True)
            pages = []
            for index, part in enumerate(parts, 1):
                image = render(part, signed, date, number, index, len(parts), font, profile, rng)
                ext = "jpg" if profile in ("jpeg", "severe", "low") else "png"
                path = folder / f"test-{number:04d}-{index}.{ext}"
                image.save(path, quality=rng.randint(23, 49)) if ext == "jpg" else image.save(path)
                pages.append({"file": path.relative_to(output).as_posix(),
                              "rows": [{**{k: v for k, v in row.items() if k not in {"label", "style", "canonical_subject"}},
                                        "subject": row.get("canonical_subject", row["subject"])} for row in part]})
            manifest.write(json.dumps({"id": number, "split": split, "test_only": True,
                                       "date": date.isoformat(), "signed": signed.isoformat(),
                                       "style": style, "profile": profile, "pages": pages,
                                       "require_review": stress and number % 5 == 0},
                                      ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument("--count", default=500, type=int)
    parser.add_argument("--stress", action="store_true", help="Практики, диапазоны, отмены и неизвестный предмет")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    output = args.output.resolve()
    site_data = Path(__file__).resolve().parents[1] / "data"
    if output.is_relative_to(site_data):
        parser.error("Use a separate synthetic directory")
    generate(output, args.font, args.count, args.stress)


if __name__ == "__main__":
    main()
