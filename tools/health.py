"""Следит за автопроверкой сайта техникума. Ведёт счётчик неудач подряд в data/health.json;
после LIMIT неудач подряд открывает задачу «сбой» (назначенную владельцу — придёт пуш),
после успеха закрывает её.

    python tools/health.py --setup success|failure --scrape success|failure --news success|failure
    python tools/health.py --alarm "что сломалось"   # сразу задача (если такой ещё нет) — для поломок
                                                       # сборки и сохранения, которые сами не пройдут

Переменные: GITHUB_TOKEN, GITHUB_REPOSITORY, HEALTH_ASSIGNEE (кому назначать задачу).
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "health.json"
LIMIT = 3  # проверка идёт раз в час (и по сигналу сторожа): 3 неудачи подряд ≈ 3 часа
LABEL = "сбой"
TITLE = "Сайт не может прочитать данные с сайта техникума"
CHECKS = {"setup": "установка программ (tesseract)", "scrape": "замены", "news": "новости"}


def now():
    return dt.datetime.now(ZoneInfo("Europe/Moscow")).isoformat(timespec="minutes")


def update(state, results, when):
    """Новый state и действие: "open" | "close" | None."""
    failing = [k for k, ok in results.items() if not ok]
    prev = state.get("failures", 0)
    if failing:
        n = prev + 1
        new = {"failures": n, "failing": failing, "since": state.get("since") or when, "last_check": when,
               "issue_open": state.get("issue_open", False)}
        action = "open" if n >= LIMIT and not new["issue_open"] else None
    else:
        new = {"failures": 0, "failing": [], "since": None, "last_check": when, "issue_open": state.get("issue_open", False)}
        action = "close" if new["issue_open"] else None
    if action == "open":
        new["issue_open"] = True
    if action == "close":
        new["issue_open"] = False
    return new, action


class Repo:
    def __init__(self, token, repo):
        self.repo = repo
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def _url(self, path):
        return f"https://api.github.com/repos/{self.repo}/{path}"

    def open_issue(self, body, assignee):
        r = requests.post(self._url("labels"), headers=self.h, json={"name": LABEL, "color": "b3261e"}, timeout=30)
        if r.status_code not in (201, 422):
            r.raise_for_status()
        data = {"title": TITLE, "body": body, "labels": [LABEL]}
        if assignee:
            data["assignees"] = [assignee]
        r = requests.post(self._url("issues"), headers=self.h, json=data, timeout=30)
        r.raise_for_status()
        return r.json()["number"]

    def has_open(self):
        r = requests.get(self._url("issues"), headers=self.h, params={"labels": LABEL, "state": "open"}, timeout=30)
        r.raise_for_status()
        return bool(r.json())

    def close_issues(self, comment):
        r = requests.get(self._url("issues"), headers=self.h, params={"labels": LABEL, "state": "open"}, timeout=30)
        r.raise_for_status()
        for issue in r.json():
            requests.post(self._url(f"issues/{issue['number']}/comments"), headers=self.h,
                          json={"body": comment}, timeout=30).raise_for_status()
            requests.patch(self._url(f"issues/{issue['number']}"), headers=self.h,
                           json={"state": "closed", "state_reason": "completed"}, timeout=30).raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    for k in CHECKS:
        ap.add_argument(f"--{k}", choices=["success", "failure", "skipped", "cancelled", ""], default="success")
    ap.add_argument("--alarm", help="сразу открыть задачу о сбое с этим текстом (если открытой ещё нет)")
    args = ap.parse_args()
    if args.alarm:
        repo = Repo(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
        run = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions"
        if repo.has_open():
            print("задача о сбое уже открыта")
        else:
            n = repo.open_issue(f"Ежечасная проверка упала: **{args.alarm}** ({now()} МСК). Сайт мог не обновиться. "
                                f"Логи: {run}", os.environ.get("HEALTH_ASSIGNEE"))
            print(f"открыта задача #{n}")
        return 0
    results = {k: getattr(args, k) != "failure" for k in CHECKS}
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    new, action = update(state, results, now())
    print(f"неудач подряд: {new['failures']}" + (f" ({', '.join(CHECKS[k] for k in new['failing'])})" if new["failing"] else ""))
    if action:
        repo = Repo(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
        run = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions"
        if action == "open":
            what = ", ".join(CHECKS[k] for k in new["failing"])
            n = repo.open_issue(
                f"Автопроверка {new['failures']} раз подряд не смогла получить: **{what}** (с {new['since']} МСК).\n\n"
                f"Сайт показывает последние сохранённые данные. Возможные причины: сайт техникума недоступен "
                f"или у него поменялась вёрстка. Логи: {run}\n\n"
                f"Задача закроется сама, когда проверка снова пройдёт.", os.environ.get("HEALTH_ASSIGNEE"))
            print(f"открыта задача #{n}")
        else:
            repo.close_issues(f"Проверка снова проходит ({new['last_check']} МСК).")
            print("задача о сбое закрыта")
    # файл меняется только при смене состояния — без лишних коммитов каждые 2 часа
    keep = {k: v for k, v in new.items() if k != "last_check"}
    old = {k: v for k, v in state.items() if k != "last_check"}
    if keep != old:
        STATE.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
