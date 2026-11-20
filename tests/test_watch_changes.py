import datetime as dt
import hashlib
import json
from types import SimpleNamespace

import pytest
from tools.watch_changes import changed_documents


HTML = '<div class="com-content-article__body"><p>на 20 ноября 2026 года очное отделение</p>{}</div>'
TODAY = dt.date(2026, 11, 20)


def fetch(url, **kwargs):
    return SimpleNamespace(content=b"original", raise_for_status=lambda: None)


def test_unknown_document_triggers_check(tmp_path):
    assert changed_documents(HTML.format('<img src="/images/order.png">'), tmp_path, fetch, TODAY) == ["2026-11-20"]


def test_unchanged_and_overwritten_image(tmp_path):
    path = tmp_path / '2026-11-20.json'
    old = {"images": [{"url": "https://utgt-pgups.ru/images/order.png", "sha1": hashlib.sha1(b"original").hexdigest()}]}
    path.write_text(json.dumps(old), encoding="utf-8")
    html = HTML.format('<img src="/images/order.png">')
    assert changed_documents(html, tmp_path, fetch, TODAY) == []
    old["images"][0]["sha1"] = "older-image"
    path.write_text(json.dumps(old), encoding="utf-8")
    assert changed_documents(html, tmp_path, fetch, TODAY) == ["2026-11-20"]


def test_removed_order_and_no_changes_text(tmp_path):
    html = HTML.format('<p>По расписанию</p>')
    assert changed_documents(html, tmp_path, fetch, TODAY) == ["2026-11-20"]
    (tmp_path / '2026-11-20.json').write_text('{"images": []}', encoding="utf-8")
    assert changed_documents(html, tmp_path, fetch, TODAY) == []


def test_wrong_layout_is_failure_not_unchanged(tmp_path):
    with pytest.raises(ValueError):
        changed_documents('<html>404</html>', tmp_path, fetch, TODAY)


def test_old_or_correspondence_document_does_not_trigger(tmp_path):
    assert changed_documents(HTML.replace('20 ноября', '1 ноября').format('<img src="/i.png">'), tmp_path, fetch, TODAY) == []
    with pytest.raises(ValueError):
        changed_documents(HTML.replace('очное', 'заочное').format('<img src="/i.png">'), tmp_path, fetch, TODAY)


def test_download_failure_does_not_hide_change(tmp_path):
    def broken(*args, **kwargs):
        raise TimeoutError("unavailable")
    with pytest.raises(TimeoutError):
        changed_documents(HTML.format('<img src="/i.png">'), tmp_path, broken, TODAY)
