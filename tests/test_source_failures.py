import sys

import pytest
import requests

import scraper
import vk_zamena
from tools import news


@pytest.mark.parametrize(("failure", "message"), [
    (403, "HTTP 403 (доступ запрещён)"),
    (404, "HTTP 404 (страница не найдена)"),
    (requests.Timeout("read"), "истекло время ожидания"),
    (requests.exceptions.SSLError("certificate"), "не удалось проверить HTTPS-сертификат"),
])
def test_official_source_failure_keeps_saved_data(failure, message, tmp_path, monkeypatch, capsys):
    called = []

    def get(*args, **kwargs):
        called.append("источник")
        if isinstance(failure, Exception):
            raise failure
        response = requests.Response()
        response.status_code = failure
        response.url = scraper.URL
        return response

    monkeypatch.setattr(sys, "argv", ["update"])
    monkeypatch.setattr(vk_zamena, "process_incoming", lambda: called.append("ВК"))
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests, "get", get)
    old_news = tmp_path / "news.json"
    old_news.write_bytes(b'{"items":[]}')
    monkeypatch.setattr(news, "OUT", old_news)
    old_order = tmp_path / "2026-11-11.json"
    old_order.write_bytes(b'{"manual":"checked"}')
    monkeypatch.setattr(scraper, "OUT_DIR", tmp_path)

    assert scraper.main() == news.main() == 1
    assert called == ["ВК", "источник", "источник"]
    assert old_news.read_bytes() == b'{"items":[]}'
    assert old_order.read_bytes() == b'{"manual":"checked"}'
    error = capsys.readouterr().err
    assert error.count(message) == 2
