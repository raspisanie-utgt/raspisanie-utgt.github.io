"""Generate labelled, offline test photos. Never write to the site's data directory."""
import argparse
import datetime as dt
import hashlib
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


def render(rows, signed, date, number, page, pages, font_path, profile, rng, compact=False):
    font = ImageFont.truetype(str(font_path), 14 if compact else 19)
    small = ImageFont.truetype(str(font_path), 12 if compact else 16)
    xs = (21, 110, 164, 606, 694) if compact else (25, 150, 245, 860, 995)
    line_height, padding, top = (16, 4, 1) if compact else (22, 8, 4)
    wrapped = [wrap(row["subject"], font, xs[3] - xs[2] - 14) for row in rows]
    heights = [max(20 if compact else 28, line_height * len(lines) + padding) for lines in wrapped]
    y = 215
    image = Image.new("L", (716 if compact else 1020, y + sum(heights) + 42), 255)
    draw = ImageDraw.Draw(image)
    draw.text((25, 19), f"ТЕСТОВОЕ РАСПОРЯЖЕНИЕ № {number} — НЕ ДЛЯ ПУБЛИКАЦИИ", font=font, fill=12)
    draw.text((25, 62), f"Подписано {signed:%d.%m.%Y}   Лист {page} из {pages}", font=font, fill=12)
    heading = "Внести изменения на" if compact else "Внести изменения в расписание учебных занятий на"
    draw.text((25, 113), f"{heading} {date:%d.%m.%Y} года", font=font, fill=12)
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
            group_y = y + (top if compact else 5)
            if row["style"] == "merged":
                end = index + 1
                while end < len(rows) and rows[end]["group"] == row["group"]:
                    end += 1
                group_y = y + (sum(heights[index:end]) - 20) // 2
            draw.text((xs[0] + 20, group_y), row["group"], font=font, fill=10)
        draw.text((xs[1] + (7 if compact else 13), y + (top if compact else 5)), f"{row['lessons'][0]}-{row['lessons'][-1]}", font=font, fill=10)
        for line_number, line in enumerate(lines):
            draw.text((xs[2] + 7, y + top + line_number * line_height), line, font=font, fill=10)
        draw.text((xs[3] + (8 if compact else 26), y + (top if compact else 5)), row["room"], font=font, fill=10)
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
    if profile == "phone":
        image = image.rotate(rng.uniform(-.35, .35), Image.Resampling.BICUBIC, fillcolor=255)
        image = image.filter(ImageFilter.GaussianBlur(.2))
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


def targeted_rows(number, style):
    rows = stress_rows(number, style)
    language = 'французский' if number % 5 == 1 else 'немецкий'
    separator = ':' if number % 4 == 2 else '/'
    rows += [dict(group='11-В', lessons=[7, 8], time=None,
                  subject=f'Иностранный язык (английский {separator} {language})',
                  canonical_subject=('Иностранный язык (английский) / Иностранный язык (немецкий)'
                                     if language == 'немецкий' else f'Иностранный язык (английский {separator} {language})'),
                  room='2-15 / 1-14', label=True, style=style),
             dict(group='11-П', lessons=[7, 8], time=None,
                  subject='Иностранный язык (немецкий) / Химия', room='1-14 / 2-7', label=True, style=style)]
    return rows


def generate(output, font, count, stress=False, compound=False, targeted=False, seed=0):
    font = Path(font)
    output.mkdir(parents=True, exist_ok=True)
    marker = output / "SYNTHETIC_ONLY"
    if not marker.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty or an existing synthetic corpus")
    marker.write_text("TEST DATA. DO NOT PUBLISH.\n", encoding="utf-8")
    (output / 'generation.json').write_text(json.dumps(dict(count=count, stress=stress, compound=compound,
        targeted=targeted, seed=seed, font=font.name, font_sha256=hashlib.sha256(font.read_bytes()).hexdigest()),
        ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / "manifest.jsonl").open("w", encoding="utf-8") as manifest:
        for number in range(count):
            split = "train" if number < count * 7 // 10 else "holdout"
            rng = random.Random((432100 if split == "train" else 961800) + number + seed + (20461120 if targeted else 0))
            date = (dt.date(2026, 11, 19) if stress or targeted else
                    dt.date(2026, 10 + (number % 3), 1) + dt.timedelta(days=number % 4))
            signed = date - dt.timedelta(days=rng.randint(2, 8))
            style = rng.choice(("merged", "blank", "explicit"))
            profiles = ("clean", "tilt", "blur", "shadow", "low", "jpeg", "phone", "severe") if targeted else ("clean", "tilt", "blur", "shadow", "low", "jpeg", "severe")
            profile = profiles[number % len(profiles)]
            size = 10 + number % 41
            rows = targeted_rows(number, style) if targeted else stress_rows(number, style) if stress else make_rows(rng, size, style)
            if compound:
                rows += [dict(group='11-П', lessons=[7, 8], time=None,
                              subject='Иностранный язык (немецкий) / Химия', room='1-14 / 2-7', label=True, style=style),
                         dict(group='11-В', lessons=[7, 8], time=None,
                              subject='Иностранный язык (английский / немецкий)',
                              canonical_subject='Иностранный язык (английский) / Иностранный язык (немецкий)',
                              room='2-15 / 1-14', label=True, style=style)]
            size = len(rows)
            # Keep a page break in the middle of some groups. A repeated label starts each page.
            cut = rng.randint(size // 3, size * 2 // 3)
            parts = [rows[:cut], rows[cut:]] if number % 5 == 0 else [rows]
            folder = output / split
            folder.mkdir(exist_ok=True)
            pages = []
            for index, part in enumerate(parts, 1):
                image = render(part, signed, date, number, index, len(parts), font, profile, rng,
                               compact=targeted and (number // len(profiles)) % 2 == 0)
                ext = "jpg" if profile in ("jpeg", "severe", "low", "phone") else "png"
                path = folder / f"test-{number:04d}-{index}.{ext}"
                image.save(path, quality=rng.randint(65, 85) if profile == "phone" else rng.randint(23, 49)) if ext == "jpg" else image.save(path)
                pages.append({"file": path.relative_to(output).as_posix(),
                              "rows": [{**{k: v for k, v in row.items() if k not in {"label", "style", "canonical_subject"}},
                                        "subject": row.get("canonical_subject", row["subject"])} for row in part]})
            manifest.write(json.dumps({"id": number, "split": split, "test_only": True,
                                       "date": date.isoformat(), "signed": signed.isoformat(),
                                       "style": style, "profile": profile, "pages": pages,
                                       "compact": targeted and (number // len(profiles)) % 2 == 0,
                                       "require_review": (number % 5 in (0, 1)) if targeted else stress and number % 5 == 0},
                                      ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument("--count", default=500, type=int)
    parser.add_argument("--stress", action="store_true", help="Практики, диапазоны, отмены и неизвестный предмет")
    parser.add_argument("--compound", action="store_true", help="Добавить составные дисциплины и языковые подгруппы")
    parser.add_argument("--targeted", action="store_true", help="Мелкие строки, языковые пары и неизвестные дисциплины")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    output = args.output.resolve()
    site_data = Path(__file__).resolve().parents[1] / "data"
    if output.is_relative_to(site_data):
        parser.error("Use a separate synthetic directory")
    generate(output, args.font, args.count, args.stress, args.compound, args.targeted, args.seed)


if __name__ == "__main__":
    main()
