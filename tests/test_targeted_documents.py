import collections
import datetime as dt
import json
from pathlib import Path
import shutil

import pytest

import scraper
from tools import vk_zamena
from tools.compare_vk_ocr import row_key

FIX = Path(__file__).parent / 'fixtures'


@pytest.mark.skipif(shutil.which('tesseract') is None, reason='нет tesseract')
@pytest.mark.parametrize('label', [
    'targeted-phone', 'targeted-shadow', 'targeted-low', 'targeted-unknown-language'])
def test_targeted_documents_publish_only_exact_confirmed_data(label, tmp_path, monkeypatch):
    candidates = [p for p in FIX.glob(label + '.*') if p.suffix != '.json']
    assert len(candidates) == 1
    case = json.loads((FIX / (label + '.json')).read_text(encoding='utf-8'))
    monkeypatch.setattr(vk_zamena, 'add_ai_suggestion', lambda *args: None)
    tables = []
    original = scraper.ocr_table
    def capture(*args, **kwargs):
        table = original(*args, **kwargs)
        if not kwargs.get('alternate'):
            tables.append(table)
        return table
    monkeypatch.setattr(scraper, 'ocr_table', capture)
    result = vk_zamena.publish(candidates, tmp_path, dt.date.fromisoformat(case['date']), dry=True)
    assert not list(tmp_path.iterdir())
    if case['require_review']:
        assert result['status'] == 'uncertain'
        return
    if label != 'targeted-low':
        assert result['status'] == 'ok'
    if result['status'] == 'ok':
        truth = collections.Counter(row_key(r['group'], r) for p in case['pages'] for r in p['rows'])
        actual = collections.Counter(row_key(r['group'], r) for table in tables for r in table['rows'])
        assert actual == truth
