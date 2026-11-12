"""Последние новости с сайта УТЖТ и посты сообщества ВКонтакте -> data/news.json (заголовок, дата, ссылка).

Посты ВК берутся, только если задан ключ доступа VK_SERVICE_TOKEN (сервисный ключ приложения ВК,
хранится в секретах GitHub). Без ключа — только новости сайта, прежние посты ВК остаются.

    python tools/news.py
    python tools/news.py --html сохранённая_страница.html
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests

import utgt_net  # noqa: E402
from bs4 import BeautifulSoup

URL = "https://utgt-pgups.ru/novosti.html"
OUT = Path(__file__).resolve().parent.parent / "data" / "news.json"
LIMIT = 10
# Новости про СВО, беспилотники и военную службу на сайт не попадают (проверяются заголовок и текст)
BLOCK = re.compile(r"\bСВО\b|специальн\w*\s+военн\w*\s+операц|беспилот|\bБПЛА\b|\bБАС\b|\bдрон|"
                   r"военн\w*\s+служб\w*\s+по\s+контракт|контрактн\w*\s+служб|мобилизац|Минобороны|"
                   r"Министерств\w*\s+обороны|участник\w*\s+СВО|зон\w*\s+СВО", re.I)
VK_GROUP = 214137  # https://vk.com/club214137 — официальное сообщество УТЖТ
SHORT = 200  # пост короче — показывается целиком, длиннее — только первая строка
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
MSK = timezone(timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0 (utgt schedule bot; +https://github.com/raspisanie-utgt/raspisanie-utgt.github.io)"}


def parse(html, base=URL):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for it in soup.select(".com-content-category-blog__item, .blog-item")[:LIMIT]:
        h = it.select_one(".page-header h2, h2")
        link = it.select_one("p.readmore a, .page-header a, figure a, h2 a")
        if not h or not link:
            continue
        t = it.select_one("time")
        date = " ".join(t.get_text(" ").replace("Создано:", "").split()) if t else ""
        items.append({"title": " ".join(h.get_text(" ").split()), "date": date,
                      "url": urljoin(base, link.get("href", ""))})
    return items


def article_text(url):
    r = requests.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    body = soup.select_one(".com-content-article, .item-page, article") or soup
    return " ".join(body.get_text(" ").split())


def day_of(date):
    """«05 октября 2026» -> «2026-10-05» (для сортировки вместе с постами ВК)."""
    m = re.match(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", date or "", re.I)
    if not m or m.group(2).lower() not in MONTHS:
        return ""
    return f"{m.group(3)}-{MONTHS.index(m.group(2).lower()) + 1:02d}-{int(m.group(1)):02d}"


def vk_title(text):
    """Короткий пост — весь текст, длинный — первая строка. Без хэштегов и разметки ссылок ВК."""
    text = re.sub(r"\[(?:club|public|id)\d+\|([^\]]+)\]", r"\1", text or "")
    text = re.sub(r"#[\w@]+", "", text)
    lines = [" ".join(x.split()) for x in text.splitlines()]
    lines = [x for x in lines if x]
    if not lines:
        return ""
    whole = " ".join(lines)
    if len(whole) <= SHORT:
        return whole
    first = lines[0]
    return first if len(first) <= SHORT else first[:SHORT].rsplit(" ", 1)[0] + "…"


def vk_parse(posts):
    if not isinstance(posts, list):
        raise ValueError("Некорректный список постов ВК")
    items = []
    malformed = False
    for p in posts:
        if not isinstance(p, dict):
            malformed = True
            continue
        if p.get("marked_as_ads"):
            continue
        text = p.get("text")
        if not text:
            copies = p.get("copy_history") or []
            if not isinstance(copies, list):
                malformed = True
                continue
            first = copies[0] if copies else {}
            text = first.get("text", "") if isinstance(first, dict) else None
        if not isinstance(text, str):
            malformed = True
            continue
        title = vk_title(text)
        if not title:
            continue
        post_id, timestamp = p.get("id"), p.get("date")
        if type(post_id) is not int or post_id <= 0 or type(timestamp) is not int or timestamp < 0:
            malformed = True
            continue
        try:
            d = datetime.fromtimestamp(timestamp, MSK)
        except (OverflowError, OSError, ValueError):
            malformed = True
            continue
        items.append({"title": title, "date": f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}", "day": d.strftime("%Y-%m-%d"),
                      "url": f"https://vk.com/wall-{VK_GROUP}_{post_id}", "from": "vk", "text": text})
    if malformed and not items:
        raise ValueError("Из повреждённого ответа ВК не удалось прочитать ни одного поста")
    return items


class VKAPIError(RuntimeError):
    def __init__(self, error):
        code = error.get("error_code") if isinstance(error, dict) else None
        self.code = code if type(code) is int and 0 < code <= 9999 else None
        super().__init__("Ошибка API ВК")


def vk_posts(token):
    r = requests.get("https://api.vk.com/method/wall.get", timeout=60, headers=UA,
                     params={"owner_id": -VK_GROUP, "count": 15, "v": "5.199", "access_token": token})
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise VKAPIError(data["error"])
    return vk_parse(data["response"]["items"])


def blocked(item, text):
    return bool(BLOCK.search(item["title"]) or BLOCK.search(text or ""))


def college_news(html_path):
    if html_path:
        html = Path(html_path).read_text(encoding="utf-8")
    else:
        try:
            r = requests.get(URL, timeout=60, headers=UA)
            r.raise_for_status()
        except requests.RequestException as error:
            print(f"Страница новостей техникума: {utgt_net.failure_reason(error)}. Сохранённые новости остаются на сайте.",
                  file=sys.stderr)
            return None
        r.encoding = "utf-8"
        html = r.text
    items = parse(html)
    if not items:
        print("ВНИМАНИЕ: новости не найдены — возможно, поменялась вёрстка", file=sys.stderr)
        return None
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html")
    args = ap.parse_args()
    # текст каждой новости проверяется один раз: решения хранятся в news.json (hidden / checked)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    hidden, checked = set(old.get("hidden", [])), set(old.get("checked", []))
    cached = old.get("cached", {})
    previous = old.get("items", [])
    college = college_news(args.html)
    if college is not None:
        for it in college:
            url, text = it["url"], ""
            if url not in checked and not args.html:
                try:
                    text = article_text(url)
                except requests.RequestException:
                    pass  # не открылась — решаем по заголовку, проверим текст в следующий раз
                else:
                    checked.add(url)
            if blocked(it, text):
                hidden.add(url)
            it["day"] = day_of(it["date"])
        checked.intersection_update(it["url"] for it in college)
    # посты ВК: текст уже есть, проверяется сразу; если ВК не ответил — остаются прежние посты
    token = os.environ.get("VK_SERVICE_TOKEN")
    vk = None
    if not args.html and not token:
        print("ВК: обновление пропущено — не настроен VK_SERVICE_TOKEN.", file=sys.stderr)
    elif token and not args.html:
        try:
            vk = vk_posts(token)
        except VKAPIError as e:
            code = f", код {e.code}" if e.code is not None else ""
            print(f"ВК не ответил (ошибка API{code}). Сохранённые посты остаются на сайте.", file=sys.stderr)
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            print(f"ВК не ответил ({type(e).__name__}). Сохранённые посты остаются на сайте.", file=sys.stderr)
        else:
            for it in vk:
                if blocked(it, it.pop("text")):
                    hidden.add(it["url"])
    if college is None and vk is None:
        return 1

    vk_updated = vk is not None
    current = {it["url"] for source in (college, vk) if source is not None for it in source}
    vk_prefix = f"https://vk.com/wall-{VK_GROUP}_"
    hidden = {url for url in hidden if url in current or (vk if url.startswith(vk_prefix) else college) is None}
    if college is None:
        college = cached.get("college", [it for it in previous if it.get("from") != "vk"])
    if vk is None:
        vk = cached.get("vk", [it for it in previous if it.get("from") == "vk"])

    def unique(source):
        result = {}
        for it in sorted(source, key=lambda it: it.get("day", ""), reverse=True):
            if it["url"] not in hidden:
                result.setdefault(it["url"], it)
        return list(result.values())

    college, vk = unique(college), unique(vk)
    shown = unique(college + vk)[:LIMIT]
    if vk_updated:
        print(f"ВК: доступно {len(vk)} постов после фильтрации, в ленте {sum(it.get('from') == 'vk' for it in shown)}.")
    new = json.dumps({"source": URL, "items": shown, "hidden": sorted(hidden), "checked": sorted(checked),
                      "cached": {"college": college[:LIMIT], "vk": vk[:LIMIT]}},
                     ensure_ascii=False, indent=1)
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != new:
        OUT.write_text(new, encoding="utf-8")
    print(f"новостей: {len(shown)} (скрыто: {len(hidden)}), последняя: {shown[0]['date'] if shown else '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
