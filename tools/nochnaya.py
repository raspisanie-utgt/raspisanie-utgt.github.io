"""Итог ночной полной проверки (.github/workflows/nochnaya.yml) -> задача на GitHub с меткой «ночная проверка».

Нашлись проблемы — открывает задачу (или дописывает в уже открытую), всё чисто — закрывает открытую.

    python tools/nochnaya.py _proverka      # папка с выводом tests/browser/run.sh

Переменные: GITHUB_TOKEN, GITHUB_REPOSITORY, HEALTH_ASSIGNEE, RUN_URL — без ключа только печатает.
"""
import os
import re
import sys
from pathlib import Path

import requests

LABEL = "ночная проверка"


def report(folder):
    """(всего проблем, текст для задачи)."""
    folder = Path(folder)
    summary = (folder / "svodka.txt").read_text(encoding="utf-8") if (folder / "svodka.txt").exists() else ""
    total = sum(int(n) for n in re.findall(r"проблем:\s*(\d+)", summary))
    if not summary:
        total = 1
    lines = []
    for f in sorted(folder.glob("[0-9][0-9]_*.txt")):
        bad = [x.rstrip() for x in f.read_text(encoding="utf-8", errors="replace").splitlines() if x.startswith("  - ")]
        if bad:
            lines.append(f"**{f.stem}**")
            lines += bad[:15] + ([f"  - … и ещё {len(bad) - 15}"] if len(bad) > 15 else [])
    text = "Сводка:\n```\n" + (summary.strip() or "сводки нет — проверка не дошла до конца") + "\n```\n\n" + "\n".join(lines)
    return total, text


def main(folder):
    total, text = report(folder)
    print(text)
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return 0
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    run = os.environ.get("RUN_URL", "")
    requests.post(f"{api}/labels", headers=h, json={"name": LABEL, "color": "d93f0b"}, timeout=30)
    r = requests.get(f"{api}/issues", headers=h, params={"labels": LABEL, "state": "open"}, timeout=30)
    r.raise_for_status()
    open_issues = r.json()
    if total == 0:
        for i in open_issues:
            requests.post(f"{api}/issues/{i['number']}/comments", headers=h, timeout=30,
                          json={"body": f"Ночная проверка прошла без замечаний. {run}"})
            requests.patch(f"{api}/issues/{i['number']}", headers=h, json={"state": "closed", "state_reason": "completed"}, timeout=30)
        return 0
    body = f"Ночная полная проверка сайта нашла проблем: {total}. Запуск: {run}\n\n{text}"
    if open_issues:
        requests.post(f"{api}/issues/{open_issues[0]['number']}/comments", headers=h, json={"body": body[:60000]}, timeout=30)
    else:
        data = {"title": "Ночная полная проверка нашла проблемы", "labels": [LABEL], "body": body[:60000]}
        if os.environ.get("HEALTH_ASSIGNEE"):
            data["assignees"] = [os.environ["HEALTH_ASSIGNEE"]]
        requests.post(f"{api}/issues", headers=h, json=data, timeout=30).raise_for_status()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "_proverka"))
