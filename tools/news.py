"""Последние новости с сайта УТЖТ и посты сообщества ВКонтакте -> data/news.json (заголовок, дата, ссылка).

Посты ВК берутся, только если задан ключ доступа VK_SERVICE_TOKEN (сервисный ключ приложения ВК,
хранится в секретах GitHub). Без ключа — только новости сайта, прежние посты ВК остаются.
Если сайт недоступен, сохраняются его прежние новости и обновляются посты ВК при наличии ключа.

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

import utgt_net  # noqa: F401,E402 — https к сайту техникума не работает -> http
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
    items = []
    for p in posts:
        if p.get("marked_as_ads"):
            continue
        text = p.get("text") or ((p.get("copy_history") or [{}])[0].get("text") or "")
        title = vk_title(text)
        if not title:
            continue
        d = datetime.fromtimestamp(p["date"], MSK)
        items.append({"title": title, "date": f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}", "day": d.strftime("%Y-%m-%d"),
                      "url": f"https://vk.com/wall-{VK_GROUP}_{p['id']}", "from": "vk", "text": text})
    return items


def vk_posts(token):
    r = requests.get("https://api.vk.com/method/wall.get", timeout=60, headers=UA,
                     params={"owner_id": -VK_GROUP, "count": 15, "v": "5.199", "access_token": token})
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("error_msg", "ошибка ВК"))
    return vk_parse(data["response"]["items"])


def blocked(item, text):
    return bool(BLOCK.search(item["title"]) or BLOCK.search(text or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html")
    args = ap.parse_args()
    try:
        if args.html:
            html = Path(args.html).read_text(encoding="utf-8")
        else:
            r = requests.get(URL, timeout=60, headers=UA)
            r.raise_for_status()
            r.encoding = "utf-8"
            html = r.text
    except requests.RequestException as e:
        print(f"Сайт техникума не ответил: {e}", file=sys.stderr)
        items = []
    else:
        items = parse(html)
        if not items:
            print("ВНИМАНИЕ: новости не найдены — возможно, поменялась вёрстка", file=sys.stderr)
    site_ok = bool(items)
    if args.html and not site_ok:
        return 1
    # текст каждой новости проверяется один раз: решения хранятся в news.json (hidden / checked)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    hidden, checked = set(old.get("hidden", [])), set(old.get("checked", []))
    for it in items:
        if it["url"] in checked or args.html:
            continue
        try:
            text = article_text(it["url"])
        except requests.RequestException:
            text = ""  # не открылась — решаем по заголовку, проверим текст в следующий раз
        else:
            checked.add(it["url"])
        if blocked(it, text):
            hidden.add(it["url"])
    for it in items:
        if blocked(it, ""):
            hidden.add(it["url"])
    for it in items:
        it["day"] = day_of(it["date"])
    # посты ВК: текст уже есть, проверяется сразу; если ВК не ответил — остаются прежние посты
    token = os.environ.get("VK_SERVICE_TOKEN")
    vk = [it for it in old.get("items", []) if it.get("from") == "vk"]
    vk_updated = False
    if token and not args.html:
        try:
            vk = vk_posts(token)
        except (requests.RequestException, RuntimeError, KeyError, ValueError) as e:
            # Ошибка HTTP может содержать URL запроса с токеном ВК.
            print(f"ВК не ответил: {type(e).__name__}", file=sys.stderr)
        else:
            vk_updated = True
            for it in vk:
                if blocked(it, it.pop("text")):
                    hidden.add(it["url"])
    if not site_ok:
        if not vk_updated:
            return 1
        items = old.get("cached_site_items")
        if items is None:
            items = [it for it in old.get("items", []) if it.get("from") != "vk"]
    site_items = items
    items = sorted(items + vk, key=lambda it: it["day"], reverse=True)
    shown = [it for it in items if it["url"] not in hidden][:LIMIT]
    urls = {it["url"] for it in items}
    if site_ok:
        hidden &= urls
        checked &= urls
    payload = {"source": URL, "items": shown, "hidden": sorted(hidden), "checked": sorted(checked)}
    if not site_ok:
        # Посты ВК могут вытеснить новости сайта из первых LIMIT записей.
        payload["cached_site_items"] = site_items
    new = json.dumps(payload, ensure_ascii=False, indent=1)
    if not OUT.exists() or OUT.read_text(encoding="utf-8") != new:
        OUT.write_text(new, encoding="utf-8")
    print(f"новостей: {len(shown)} (скрыто: {len(hidden & urls)}), последняя: {shown[0]['date'] if shown else '—'}")
    return 0 if site_ok else 1  # health.py учитывает доступность сайта техникума


if __name__ == "__main__":
    sys.exit(main())
