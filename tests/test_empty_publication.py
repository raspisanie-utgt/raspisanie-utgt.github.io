import copy
import scraper


def test_failed_empty_ocr_retains_previous_rows_with_warning():
    old = {'all_changes': {'21-С': [{'lessons': [5, 6], 'subject': 'Физика'}]}, 'title': 'Четверг', 'groups_in_order': ['21-С']}
    meta = {'images': [{'sha1': 'new'}], 'ocr_ok': False, 'all_changes': {}, 'title': '', 'groups_in_order': []}
    scraper.retain_previous_on_failure(meta, old)
    assert meta['all_changes'] == old['all_changes']
    assert meta['ocr_uncertain'] and not meta['ocr_ok'] and meta['retained_previous']
    assert meta['images'][0]['sha1'] == 'new'


def test_no_retention_for_deliberate_no_images_or_successful_result():
    old = {'all_changes': {'21-С': [{'subject': 'Физика'}]}}
    for meta in [{'images': [], 'ocr_ok': True, 'all_changes': {}},
                 {'images': [{}], 'ocr_ok': True, 'all_changes': {'21-С': [{'subject': 'Химия'}]}}]:
        before = copy.deepcopy(meta)
        scraper.retain_previous_on_failure(meta, old)
        assert meta == before


def test_failed_first_document_is_marked_uncertain():
    meta = {'images': [{}], 'ocr_ok': False, 'all_changes': {}}
    scraper.retain_previous_on_failure(meta, None)
    assert meta['ocr_uncertain']


def test_order82_verified_reference_and_correction():
    import json
    from pathlib import Path
    meta = json.loads((Path(scraper.ROOT) / 'data/zameny/2026-11-26.json').read_text(encoding='utf-8'))
    changes = meta['all_changes']
    assert len(changes) == 16 and sum(map(len, changes.values())) == 27
    assert meta['ocr_ok'] and meta['checked_by_hand']
    assert changes['21-С'][1]['subject'] == 'МДК.01.01'
    assert changes['21-С'][1]['room'] == '1-32'
    assert changes['11-П'][0]['room'] == '1-28 / 1-24'
    assert changes['11-А'][0]['room'] == '1-25 / 1-24'
    assert changes['11-Л'][0]['room'] == '2-10 / 1-24'
