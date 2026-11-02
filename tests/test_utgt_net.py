"""Запасной путь к сайту техникума по http, когда https не отвечает (tools/utgt_net.py)."""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import utgt_net  # noqa: E402


def test_fallback_to_http(monkeypatch):
    calls = []

    def fake(self, method, url, *a, **kw):
        calls.append(url)
        if url.startswith("https://utgt-pgups.ru"):
            raise requests.exceptions.ConnectTimeout("нет https")
        return "ok " + url
    monkeypatch.setattr(utgt_net, "_orig", fake)
    monkeypatch.setattr(utgt_net, "_https_dead", False)
    s = requests.Session()
    assert s.request("GET", "https://utgt-pgups.ru/zamena.html", timeout=60) == "ok http://utgt-pgups.ru/zamena.html"
    assert s.request("GET", "https://utgt-pgups.ru/img.png") == "ok http://utgt-pgups.ru/img.png"  # дальше сразу http
    assert calls == ["https://utgt-pgups.ru/zamena.html", "http://utgt-pgups.ru/zamena.html", "http://utgt-pgups.ru/img.png"]
    # другие сайты — как было
    assert s.request("GET", "https://api.github.com/x") == "ok https://api.github.com/x"
    assert not utgt_net.ours("https://utgt-pgups.ru.evil.com/x") and utgt_net.ours("https://www.utgt-pgups.ru/x")
