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


def failure_reason(error):
    if isinstance(error, requests.HTTPError) and error.response is not None:
        code = error.response.status_code
        detail = {403: "доступ запрещён", 404: "страница не найдена"}.get(code)
        return f"HTTP {code}" + (f" ({detail})" if detail else "")
    if isinstance(error, requests.Timeout):
        return "истекло время ожидания ответа"
    if isinstance(error, requests.exceptions.SSLError):
        return "не удалось проверить HTTPS-сертификат или установить защищённое соединение"
    if isinstance(error, requests.ConnectionError):
        return "не удалось установить соединение"
    return type(error).__name__


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
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        _https_dead = True
        print(f"HTTPS к {HOST}: {failure_reason(error)} — пробую HTTP")
        return _orig(self, method, plain, *args, **kwargs)


requests.Session.request = _request
