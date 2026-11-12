"""Фильтр новостей: про СВО, беспилотники и военную службу на сайт не попадают."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def test_official_vk_wall_updates_during_college_outage(monkeypatch, tmp_path, capsys):
    path = tmp_path / "news.json"
    college = {"title": "Новости колледжа", "date": "05 октября 2026",
               "day": "2026-10-05", "url": news.URL + "?article=1"}
    old_vk = {"title": "Старый пост", "day": "2026-10-04", "date": "04 октября 2026",
              "url": "https://vk.com/wall-214137_1", "from": "vk"}
    path.write_text(json.dumps({"items": [college, old_vk], "checked": [college["url"]]}), encoding="utf-8")
    monkeypatch.setattr(news, "OUT", path)
    monkeypatch.setattr(sys, "argv", ["news.py"])
    monkeypatch.setenv("VK_SERVICE_TOKEN", "unit-test-placeholder")
    date = int(datetime(2026, 11, 12, tzinfo=timezone.utc).timestamp())
    posts = [{"id": i, "date": date, "text": f"Студенческая новость {i}"} for i in range(2, 13)]
    posts += [None, {"id": 15, "date": "invalid", "text": "Повреждённый пост"},
              posts[0], {"id": 13, "date": date, "text": "Реклама", "marked_as_ads": 1},
              {"id": 14, "date": date, "text": "Встреча со студентами\n" + "новость " * 30 + " БПЛА"}]

    def get(url, **kwargs):
        if url == news.URL:
            raise requests.Timeout
        assert url == "https://api.vk.com/method/wall.get"
        assert kwargs["params"]["owner_id"] == -214137
        assert kwargs["params"]["v"] == "5.199"
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"response": {"items": posts}}).encode()
        return response

    monkeypatch.setattr(news.requests, "get", get)
    assert news.main() == 0
    updated = json.loads(path.read_text(encoding="utf-8"))
    urls = [item["url"] for item in updated["items"]]
    assert len(urls) == len(set(urls)) == news.LIMIT
    assert all("text" not in item for item in updated["items"])
    assert updated["cached"]["college"] == [college]
    assert updated["checked"] == [college["url"]]
    assert updated["hidden"] == ["https://vk.com/wall-214137_14"]
    assert old_vk["url"] not in urls and "https://vk.com/wall-214137_13" not in urls
    assert news.main() == 0
    assert json.loads(path.read_text(encoding="utf-8")) == updated
    before = path.read_bytes()
    posts[:] = [None, {"id": 15, "date": "invalid", "text": "Повреждённый пост"}]
    assert news.main() == 1
    assert path.read_bytes() == before

    def outage(url, **kwargs):
        raise requests.ConnectionError("unit-test-placeholder")

    monkeypatch.setattr(news.requests, "get", outage)
    assert news.main() == 1
    assert path.read_bytes() == before
    assert "unit-test-placeholder" not in capsys.readouterr().err

    monkeypatch.setattr(news, "college_news", lambda _: [college.copy()])
    assert news.main() == 0
    assert json.loads(path.read_text(encoding="utf-8")) == updated


def test_vk_diagnostics_distinguish_missing_config_from_api_failure(monkeypatch, tmp_path, capsys):
    path = tmp_path / "news.json"
    college = {"title": "Новости колледжа", "date": "05 октября 2026", "url": news.URL}
    monkeypatch.setattr(news, "OUT", path)
    monkeypatch.setattr(sys, "argv", ["news.py"])
    monkeypatch.setattr(news, "college_news", lambda _: [college.copy()])
    monkeypatch.setattr(news, "article_text", lambda _: "")
    monkeypatch.delenv("VK_SERVICE_TOKEN", raising=False)
    assert news.main() == 0
    assert "не настроен VK_SERVICE_TOKEN" in capsys.readouterr().err

    monkeypatch.setenv("VK_SERVICE_TOKEN", "unit-test-placeholder")
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps({"error": {"error_code": 5, "error_msg": "unit-test-placeholder"}}).encode()
    monkeypatch.setattr(news.requests, "get", lambda *args, **kwargs: response)
    assert news.main() == 0
    log = capsys.readouterr().err
    assert "код 5" in log
    assert "unit-test-placeholder" not in log

    response._content = b'{"response":{"items":[]}}'
    assert news.main() == 0
    assert "ВК: доступно 0 постов после фильтрации, в ленте 0." in capsys.readouterr().out
