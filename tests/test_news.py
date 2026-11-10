"""Фильтр новостей: про СВО, беспилотники и военную службу на сайт не попадают."""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import news  # noqa: E402
from news import blocked  # noqa: E402


def test_military_news_blocked():
    assert blocked({"title": "Обучение по Эксплуатации беспилотных авиационных систем"}, "")
    assert blocked({"title": "Встреча со студентами"}, "Рассказали об участниках СВО и службе")
    assert blocked({"title": "Новость"}, "Набор на военную службу по контракту")
    assert not blocked({"title": "С Днем рождения, УТЖТ! Нам 82 года!"}, "Поздравляем всех с праздником, свободный вход")
    assert not blocked({"title": "«Строками прошедших лет: подвиг солдата»"}, "Великая Отечественная война")


def test_vk_posts():
    from news import vk_parse, vk_title, day_of
    assert day_of("05 октября 2026") == "2026-10-05"
    assert vk_title("Коротко [club214137|УТЖТ] #утжт") == "Коротко УТЖТ"
    long = "Первая строка поста\n" + "много текста " * 30
    assert vk_title(long) == "Первая строка поста"
    it = vk_parse([{"id": 7, "date": 1793350800, "text": "Привет!"}, {"id": 8, "date": 1, "text": ""}])
    assert len(it) == 1 and it[0]["url"] == "https://vk.com/wall-214137_7" and it[0]["from"] == "vk"


@pytest.fixture
def cached_news(tmp_path, monkeypatch):
    out = tmp_path / "news.json"
    saved = {
        "source": news.URL,
        "items": [{"title": "Новость сайта", "url": f"{news.URL}/saved",
                   "date": "05 октября 2026", "day": "2026-10-05"}],
        "hidden": [f"{news.URL}/hidden"],
        "checked": [f"{news.URL}/hidden", f"{news.URL}/saved"],
    }
    out.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(news, "OUT", out)
    monkeypatch.setattr(sys, "argv", ["news.py"])
    monkeypatch.setenv("VK_SERVICE_TOKEN", "test-token")
    return saved


@pytest.mark.parametrize("site_error", [True, False])
def test_news_updates_vk_when_site_fails(monkeypatch, cached_news, site_error):
    def site_response(*args, **kwargs):
        if site_error:
            raise requests.ConnectTimeout("сайт недоступен")
        response = requests.Response()
        response.status_code = 200
        response._content = b"<html></html>"
        return response

    monkeypatch.setattr(news.requests, "get", site_response)
    monkeypatch.setattr(news, "vk_posts", lambda token: news.vk_parse([
        {"id": 7, "date": 1793350800, "text": "Новый пост"},
        {"id": 8, "date": 1793350800, "text": "Новости СВО"},
    ]))

    assert news.main() == 1
    updated = json.loads(news.OUT.read_text(encoding="utf-8"))
    assert [item["title"] for item in updated["items"]] == ["Новый пост", "Новость сайта"]
    assert "text" not in updated["items"][0]
    assert updated["checked"] == cached_news["checked"]
    assert set(updated["hidden"]) == {*cached_news["hidden"], "https://vk.com/wall-214137_8"}


def test_news_keeps_cache_when_both_sources_fail(monkeypatch, cached_news, capsys):
    def unavailable(*args, **kwargs):
        raise requests.ConnectTimeout("сайт недоступен")

    def vk_unavailable(token):
        raise requests.HTTPError(f"VK URL contains access_token={token}")

    monkeypatch.setattr(news.requests, "get", unavailable)
    monkeypatch.setattr(news, "vk_posts", vk_unavailable)

    assert news.main() == 1
    assert json.loads(news.OUT.read_text(encoding="utf-8")) == cached_news
    assert "test-token" not in capsys.readouterr().err


def test_news_keeps_site_items_displaced_by_vk(monkeypatch, cached_news):
    def unavailable(*args, **kwargs):
        raise requests.ConnectTimeout("сайт недоступен")

    posts = [{"id": i, "date": 1793350800, "text": f"Пост {i}"} for i in range(news.LIMIT)]
    monkeypatch.setattr(news.requests, "get", unavailable)
    monkeypatch.setattr(news, "vk_posts", lambda token: news.vk_parse(posts))

    assert news.main() == 1
    updated = json.loads(news.OUT.read_text(encoding="utf-8"))
    assert all(item["from"] == "vk" for item in updated["items"])

    posts.clear()
    assert news.main() == 1
    updated = json.loads(news.OUT.read_text(encoding="utf-8"))
    assert updated["items"] == cached_news["items"]
