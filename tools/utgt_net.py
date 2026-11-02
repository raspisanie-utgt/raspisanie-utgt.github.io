"""Связь с сайтом техникума: если защищённое подключение (https) к utgt-pgups.ru не работает — тот же адрес по
обычному (http). 02.11.2026 у них перестал работать https (браузер пишет «сайт не поддерживает защищённое
подключение»), и обновление целый день не могло забрать замены. Пользователь разрешил запасной путь по http
(страница замен общедоступная, риск подмены по дороге — маленький).

Подключить: `import utgt_net` после `import requests` — меняет поведение запросов requests только к этому сайту;
к остальным (GitHub, ВК, Гугл) — как было. Раз https в этом запуске не ответил, дальше сразу http.
"""
import requests

HOST = "utgt-pgups.ru"
CONNECT = 20  # секунд ждать подключения по https, прежде чем пробовать http
_orig = requests.Session.request
_https_dead = False


def ours(url):
    return isinstance(url, str) and url.startswith("https://") and url[8:].split("/")[0].split(":")[0] in (HOST, "www." + HOST)


def _request(self, method, url, *args, **kwargs):
    global _https_dead
    if not ours(url):
        return _orig(self, method, url, *args, **kwargs)
    plain = "http://" + url[8:]
    if _https_dead:
        return _orig(self, method, plain, *args, **kwargs)
    t = kwargs.get("timeout")
    quick = dict(kwargs, timeout=(CONNECT, t[1] if isinstance(t, tuple) else (t or 60)))
    try:
        return _orig(self, method, url, *args, **quick)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        _https_dead = True
        print(f"https к {HOST} не работает — пробую http")
        return _orig(self, method, plain, *args, **kwargs)


requests.Session.request = _request
