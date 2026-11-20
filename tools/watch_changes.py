"""Cheap independent source check. Never recognizes or publishes a document itself."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scraper


def changed_documents(html, data, get=requests.get, today=None):
    today = today or dt.datetime.now(scraper.TZ).date()
    blocks = scraper.parse_page(html)
    if not any(b["section"] == "ochnoe" for b in blocks):
        raise ValueError("Статья не содержит датированных блоков очного отделения")
    changed = []
    for block in blocks:
        date = dt.date.fromisoformat(block["date"])
        if block["section"] != "ochnoe" or not today - dt.timedelta(days=1) <= date <= today + dt.timedelta(days=14):
            continue
        path = data / (block["date"] + ".json")
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        images = []
        for url in block["images"]:
            response = get(url, timeout=45)
            response.raise_for_status()
            images.append({"url": url, "sha1": hashlib.sha1(response.content).hexdigest()})
        previous = [{"url": i["url"], "sha1": i["sha1"]} for i in old["images"]] if old else None
        if images != previous:
            changed.append(block["date"])
    return changed


def main():
    response = requests.get(scraper.URL, timeout=60)
    response.raise_for_status()
    response.encoding = "utf-8"
    changed = changed_documents(response.text, ROOT / "data" / "zameny")
    if not changed:
        print("Новых или изменённых распоряжений нет")
        return
    print("Нужна обычная проверка OCR: " + ", ".join(changed))
    api = "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
    headers = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json"}
    runs = requests.get(api + "/actions/workflows/update.yml/runs", headers=headers, params={"branch": "main", "per_page": 30}, timeout=30)
    runs.raise_for_status()
    if any(r["status"] != "completed" for r in runs.json()["workflow_runs"]):
        print("Проверка уже запущена; следующий сторож проверит результат")
        return
    dispatched = requests.post(api + "/actions/workflows/update.yml/dispatches", headers=headers, json={"ref": "main"}, timeout=30)
    dispatched.raise_for_status()
    print("Запущена обычная проверка и публикация; проверки OCR сохранены")


if __name__ == "__main__":
    main()
