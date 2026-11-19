import scraper


def test_order76_does_not_lose_chemistry_or_literature():
    vocab = scraper.subject_vocab()
    for other in ('Химия', 'Физика', 'Литература'):
        value, sure = scraper.snap_subject('Иностранный язык (немецкий) /' + other, vocab)
        assert sure
        assert value == 'Иностранный язык (немецкий) / ' + other


def test_order76_preserves_both_languages_only_with_dictionary_support():
    text = 'Иностранный язык (английский / немецкий)'
    value, sure = scraper.snap_subject(text, scraper.subject_vocab())
    assert sure
    assert value == 'Иностранный язык (английский) / Иностранный язык (немецкий)'
    assert not scraper.snap_subject(text, ['Иностранный язык (английский)'])[1]


def test_unknown_compound_part_does_not_disappear():
    value, sure = scraper.snap_subject('Химия / Несуществующая дисциплина XYZ', scraper.subject_vocab())
    assert not sure
    assert 'Несуществующая дисциплина XYZ' in value
