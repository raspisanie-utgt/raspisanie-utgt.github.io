"""Следит, не поменялись ли источники, из которых сайт собран один раз в семестр: PDF расписания занятий,
звонков, учебного графика, педсостава, и список PDF на странице «Расписания и графики». Поменялись —
открывает задачу на GitHub (сам PDF заново не разбирает: это делается вручную — tools/extract_*.py).

    python tools/sources.py           # проверить; состояние — data/sources.json (меняется только при изменениях)

Переменные: GITHUB_TOKEN, GITHUB_REPOSITORY, HEALTH_ASSIGNEE — без ключа только печатает.
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "sources.json"
PAGE = "https://utgt-pgups.ru/raspisaniya-i-grafiki.html"
UA = {"User-Agent": "Mozilla/5.0 (utgt schedule bot; +https://github.com/raspisanie-utgt/raspisanie-utgt.github.io)"}
LABEL = "источник"
# PDF на странице, за появлением новых версий которых следим (очное отделение: расписание, звонки, график)
WATCH = re.compile(r"raspisanie.*semestr|zvonk|kug.*ocn", re.I)


def tracked():
    """{название: адрес PDF} — откуда собраны данные сайта сейчас."""
    j = lambda p: json.loads((ROOT / "data" / p).read_text(encoding="utf-8"))
    out = {"расписание занятий": j("groups/index.json")["source"], "звонки": j("bells.json")["source"],
           "учебный график": j("calendar.json")["source"]}
    pdf = j("teachers.json").get("pdf")
    if pdf:
        out["педсостав"] = pdf
    return out


def fingerprint(url):
    """Размер и дата изменения файла (без скачивания); сервер не отдаёт — None."""
    r = requests.head(url, timeout=60, headers=UA, allow_redirects=True)
    if r.status_code != 200:
        return {"status": r.status_code}
    return {k: r.headers.get(h) for k, h in (("size", "Content-Length"), ("modified", "Last-Modified"), ("etag", "ETag"))
            if r.headers.get(h)}


def page_pdfs():
    r = requests.get(PAGE, timeout=60, headers=UA)
    r.raise_for_status()
    links = {urljoin(PAGE, h) for h in re.findall(r'href="([^"]+\.pdf)"', r.text, re.I)}
    return sorted(u for u in links if WATCH.search(u))


def changes(old, new):
    """Что поменялось между двумя состояниями (по ключам, которые были и раньше)."""
    out = []
    for name, cur in new.get("files", {}).items():
        prev = old.get("files", {}).get(name)
        if prev and prev["url"] == cur["url"] and prev["fp"] != cur["fp"]:
            out.append(f"**{name}**: файл на сайте техникума изменился ({prev['fp']} → {cur['fp']}) — {cur['url']}")
    if old.get("page_pdfs") is not None:
        added = sorted(set(new["page_pdfs"]) - set(old["page_pdfs"]))
        out += [f"на странице «Расписания и графики» новый PDF: {u}" for u in added]
    return out


def open_issue(text):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    requests.post(f"{api}/labels", headers=h, json={"name": LABEL, "color": "0e8a16"}, timeout=30)
    data = {"title": "Изменились исходные PDF на сайте техникума", "labels": [LABEL],
            "body": text + "\n\nСайт показывает расписание, разобранное из старых файлов. Проверить и при необходимости "
                           "разобрать заново: `tools/extract_schedule.py`, `tools/extract_calendar.py`, звонки — `data/bells.json`."}
    if os.environ.get("HEALTH_ASSIGNEE"):
        data["assignees"] = [os.environ["HEALTH_ASSIGNEE"]]
    r = requests.post(f"{api}/issues", headers=h, json=data, timeout=30)
    r.raise_for_status()
    return r.json()["number"]


def main():
    old = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    new = {"files": {}, "page_pdfs": page_pdfs()}
    for name, url in tracked().items():
        fp, prev = fingerprint(url), old.get("files", {}).get(name)
        if "status" in fp and prev and prev["url"] == url:
            fp = prev["fp"]  # сайт техникума ответил ошибкой — это не «файл изменился», сверим в следующий раз
        new["files"][name] = {"url": url, "fp": fp}
    found = changes(old, new)
    if found:
        print("\n".join(found))
        n = open_issue("\n".join("- " + f for f in found))
        if n:
            print(f"открыта задача #{n}")
    else:
        print("источники без изменений" if old else "первая проверка — запомнил источники")
    if new != old:
        STATE.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
