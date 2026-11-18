import datetime as dt
import hashlib
import json

from tools import vk_zamena


def existing_order(tmp_path, monkeypatch, **changes):
    photo = tmp_path / 'incoming.png'
    photo.write_bytes(b'test-image')
    day = '2026-11-19'
    monkeypatch.setattr(vk_zamena, 'date_from_image', lambda *args: (day, 'order'))
    meta = {'date': day, 'ocr_ok': True, 'ocr_uncertain': False,
            'ocr_group_doubt': False, 'week_doubt': False, 'groups_in_order': ['31-А'],
            'images': [{'sha1': hashlib.sha1(photo.read_bytes()).hexdigest()}]}
    meta.update(changes)
    target = tmp_path / (day + '.json')
    original = json.dumps(meta, ensure_ascii=False)
    target.write_text(original, encoding='utf-8')
    result = vk_zamena.publish([photo], out_dir=tmp_path, today=dt.date(2026, 11, 18), dry=True)
    assert target.read_text(encoding='utf-8') == original
    assert photo.read_bytes() == b'test-image'
    return result


def test_existing_uncertain_order_is_not_reported_as_verified(tmp_path, monkeypatch):
    result = existing_order(tmp_path, monkeypatch, ocr_uncertain=True)
    assert result['status'] == 'uncertain'
    assert result['published'] is True
    assert 'не подтверждено' in result['reason']


def test_different_photo_on_same_date_requires_review(tmp_path, monkeypatch):
    result = existing_order(tmp_path, monkeypatch, images=[{'sha1': 'different'}])
    assert result['status'] == 'uncertain'
    assert 'исправлением или дополнением' in result['reason']


def test_identical_verified_photo_is_already_published(tmp_path, monkeypatch):
    assert existing_order(tmp_path, monkeypatch)['status'] == 'already'
