from tools.generate_vk_ocr_cases import stress_rows

import scraper


def test_stress_corpus_uses_confirmed_canonical_subjects():
    rows = stress_rows(1, 'merged')
    vocab = set(scraper.subject_vocab())
    for row in rows:
        assert row.get('canonical_subject', row['subject']) in vocab | {'Отменить'}
    assert all(not row['room'] for row in rows if row['subject'] == 'Отменить')
    assert any(row['lessons'] == list(range(1, 7)) for row in rows)
    assert any(row['lessons'] == list(range(5, 11)) for row in rows)


def test_unknown_subject_is_test_only_and_not_in_vocabulary():
    unknown = stress_rows(0, 'explicit')[-1]['subject']
    assert unknown == 'Несуществующая дисциплина XYZ'
    assert unknown not in scraper.subject_vocab()
