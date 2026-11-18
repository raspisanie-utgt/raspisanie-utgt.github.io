from tools import vk_zamena


def test_repeat_report_explains_table_mismatch(monkeypatch):
    row = {'group': '31-А', 'lessons': [1, 2], 'time': None,
           'subject': 'Учебная практика', 'room': '1-10', 'uncertain': False,
           'raw': ['31-А', '1-2', 'Учебная практика', '1-10']}
    first = {'ok': True, 'rows': [row]}
    monkeypatch.setattr(vk_zamena.scraper, 'ocr_table', lambda *args, **kwargs:
                        {'ok': False, 'rows': [], 'group_doubt': True})
    monkeypatch.setattr(vk_zamena.scraper, 'check_with_schedule', lambda *args: None)
    report = vk_zamena.verify_ocr(['image'], [first], [], '2026-11-19', '')
    assert 'первое чтение 1, повторное 0' in report
    assert 'Сверьте' in report
    assert 'Первое чтение, строка 1: 31-А | 1-2 | Учебная практика | 1-10' in report
