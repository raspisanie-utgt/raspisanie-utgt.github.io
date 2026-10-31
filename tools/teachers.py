"""Полные ФИО преподавателей из PDF «Педагогический состав» на сайте УТЖТ -> data/teachers.json.

    python tools/teachers.py                 # скачать актуальный PDF со страницы педсостава
    python tools/teachers.py --pdf файл.pdf

В data/teachers.json: by_short — «Фамилия И.О.» (как в расписании) -> полное ФИО.
Сопоставление: точное по инициалам, иначе по фамилии и первой букве имени, если такой
преподаватель один (в расписании бывают опечатки в отчестве: «Канева О.В.» вместо «О.П.»).
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

PAGE = "https://utgt-pgups.ru/svedeniya/pedagogicheskiy-sostav.html"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "teachers.json"
FULL_RE = re.compile(r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s+([А-ЯЁ][а-яё]+)\s+"
                     r"([А-ЯЁ][а-яё]+(?:вич|вна|ична|чна|оглы|кызы))")
SHORT_RE = re.compile(r"^([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s([А-ЯЁ])\.\s?([А-ЯЁ])\.?$")
UA = {"User-Agent": "Mozilla/5.0 (utgt schedule bot; +https://github.com/raspisanie-utgt/raspisanie-utgt.github.io)"}


def full_names(pdf_path):
    """Колонка «Фамилия, имя, отчество» по всем страницам -> ['Абрамова Татьяна Юрьевна', ...]."""
    pdf = pdfplumber.open(pdf_path)
    head = pdf.pages[0].extract_words()
    fam = next(w for w in head if w["text"].startswith("Фамилия"))
    dol = next(w for w in head if w["text"].startswith("Должность"))
    x0, x1 = fam["x0"] - 15, dol["x0"] - 3
    words = [w["text"] for page in pdf.pages for w in page.extract_words()
             # только слова с заглавной: в колонку заезжает «преподаватель» из соседней
             if x0 <= w["x0"] < x1 and w["text"][:1].isupper()]
    seen, out = set(), []
    for m in FULL_RE.finditer(" ".join(words)):
        name = " ".join(m.groups())
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def norm(s):
    return s.replace("Ё", "Е").replace("ё", "е")


def match(short, full):
    """«Канева О.П.» -> «Канева Ольга Петровна» или None."""
    m = SHORT_RE.match(short.strip())
    if not m:
        return None
    sur, i1, i2 = (norm(x) for x in m.groups())
    parts = [(f, norm(f).split()) for f in full]
    exact = [f for f, p in parts if p[0] == sur and p[1][0] == i1 and p[2][0] == i2]
    if len(exact) == 1:
        return exact[0]
    loose = [f for f, p in parts if p[0] == sur and p[1][0] == i1]
    return loose[0] if len(loose) == 1 else None


def schedule_teachers():
    names = set()
    for path in sorted((ROOT / "data" / "groups").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for day in data.get("days", {}).values():
            for e in day:
                names.update(t.strip() for t in e["teacher"].split(" / ") if t.strip())
    return sorted(names)


def pdf_url():
    r = requests.get(PAGE, timeout=60, headers=UA)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    pdfs = [a for a in soup.select("a[href]") if a["href"].lower().split("?")[0].endswith(".pdf")]
    # нужен именно список педсостава: по словам в тексте ссылки или в имени файла, а не первая PDF на странице
    want = re.compile(r"педагог|педсостав|pedsostav|pedagog|sostav", re.I)
    link = next((a["href"] for a in pdfs if want.search(a.get_text(" ") + " " + a["href"])), None) or pdfs[0]["href"]
    return urljoin(PAGE, link)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf")
    args = ap.parse_args()
    source = args.pdf
    if not args.pdf:
        source = pdf_url()
        r = requests.get(source, timeout=120, headers=UA)
        r.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(r.content)
        tmp.close()
        args.pdf = tmp.name
    full = full_names(args.pdf)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if old.get("teachers") and len(full) < 0.8 * len(old["teachers"]):
        # PDF сменил вид или взяли не тот файл: не затираем хороший список пустым (сайт показал бы сокращения)
        print(f"ВНИМАНИЕ: в новом списке педсостава {len(full)} имён, было {len(old['teachers'])} — оставляю старый",
              file=sys.stderr)
        return 1
    by_short = {s: f for s in schedule_teachers() if (f := match(s, full))}
    missing = [s for s in schedule_teachers() if s not in by_short]
    OUT.write_text(json.dumps({"source": PAGE, "pdf": source if source.startswith("http") else "",
                               "teachers": full, "by_short": by_short}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"в списке педсостава: {len(full)}; найдено полное ФИО для {len(by_short)} из {len(by_short) + len(missing)}")
    if missing:
        print("нет в списке педсостава:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
