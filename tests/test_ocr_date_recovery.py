import datetime as dt

from PIL import Image

from tools import vk_zamena


def test_small_header_needs_two_matching_dates(tmp_path, monkeypatch):
    path = tmp_path / 'test.png'
    Image.new('L', (100, 200), 255).save(path)
    readings = iter(['Подписано 18.11.2026',
                     'Занятия на 19.11.2026 года', 'Занятия на 19.11.2026 года'])
    monkeypatch.setattr(vk_zamena, 'ocr_text', lambda *args, **kwargs: next(readings))
    assert vk_zamena.date_from_image(path, dt.date(2026, 11, 18))[0] == '2026-11-19'


def test_conflicting_header_dates_are_not_chosen_arbitrarily(tmp_path, monkeypatch):
    path = tmp_path / 'test.png'
    Image.new('L', (100, 200), 255).save(path)
    readings = iter(['Подписано 18.11.2026',
                     'Занятия на 19.11.2026 года', 'Занятия на 20.11.2026 года'])
    monkeypatch.setattr(vk_zamena, 'ocr_text', lambda *args, **kwargs: next(readings))
    assert vk_zamena.date_from_image(path, dt.date(2026, 11, 18))[0] is None
