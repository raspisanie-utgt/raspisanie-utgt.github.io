from PIL import Image, ImageDraw
import numpy as np
import pytest

import scraper
from tools.generate_vk_ocr_cases import targeted_rows


VOCAB = ['Иностранный язык (английский)', 'Иностранный язык (немецкий)', 'Химия', 'Физика']
PAIR = 'Иностранный язык (английский) / Иностранный язык (немецкий)'


@pytest.mark.parametrize('separator', ['/', ':', ';', '|'])
def test_two_literal_known_languages_preserve_both_subgroups(separator):
    text = f'Иностранный язык (английский {separator} немецкий)'
    assert scraper.snap_subject(text, VOCAB) == (PAIR, True)


@pytest.mark.parametrize('text', [
    'Иностранный язык (английский : французский)',
    'Иностранный язык (английский / немепкий)',
    'Иностранный язык (английский немецкий)',
    'Иностоанный язык (английский / немецкий)',
    'Пностранный язык (английский : французский)',
])
def test_incomplete_language_pair_cannot_shrink_to_one_language(text):
    assert scraper.snap_subject(text, VOCAB) == (text, False)


def test_language_pair_needs_both_official_vocabulary_entries():
    text = 'Иностранный язык (английский / немецкий)'
    assert scraper.snap_subject(text, VOCAB[:1]) == (text, False)


@pytest.mark.parametrize('readings,expected', [
    (['Иностранный язык (английский / немецкий)'] * 2, PAIR),
    (['Иностранный язык (английский / немецкий)', 'Иностранный язык (английский / немепкий)'], None),
    (['Иностранный язык (английский)'] * 2, None),
    (['Иностранный язык (английский / французский)'] * 2, None),
    (['Отменить'] * 2, None),
])
def test_recovery_requires_two_exact_complete_readings(monkeypatch, readings, expected):
    image = Image.new('L', (160, 40), 255)
    ImageDraw.Draw(image).rectangle((8, 8, 140, 28), fill=0)
    monkeypatch.setattr(scraper, 'read_binary_cell', lambda *args: 'неподтверждённый текст')
    values = iter(readings)
    monkeypatch.setattr(scraper, '_tesseract', lambda *args: next(values))
    assert scraper._reread_legacy_subject(image, (0, 0, 160, 40), VOCAB,
                                         original='Иностранный язык (английский / немепкий)') == expected


def test_legacy_recovery_cannot_drop_unknown_second_subgroup(monkeypatch):
    monkeypatch.setattr(scraper, 'read_binary_cell', lambda *args: VOCAB[0])
    assert scraper._reread_legacy_subject(Image.new('L', (160, 40), 255), (0, 0, 160, 40), VOCAB,
                                         original='Иностранный язык (английский / французский)') is None


def test_two_new_readings_cannot_replace_a_different_language(monkeypatch):
    image = Image.new('L', (160, 40), 255)
    ImageDraw.Draw(image).rectangle((8, 8, 140, 28), fill=0)
    monkeypatch.setattr(scraper, 'read_binary_cell', lambda *args: 'неподтверждённый текст')
    monkeypatch.setattr(scraper, '_tesseract', lambda *args: 'Иностранный язык (английский / немецкий)')
    assert scraper._reread_legacy_subject(image, (0, 0, 160, 40), VOCAB,
                                         original='Иностранный язык (английский / французский)') is None


def test_room_list_requires_every_component():
    known = {'2-15', '1-14'}
    assert scraper.is_known_room('2-15 / 1-14', known)
    assert scraper.snap_room('2-15; 1-14', known) == '2-15 / 1-14'
    for text in ('2-1$ / 1-14', '2-15 / неизвестно', '2-15 /', ''):
        assert not scraper.is_known_room(text, known)


def test_shadow_and_grid_are_not_text_in_an_empty_cell():
    pixels = np.tile(np.linspace(175, 190, 100).astype('uint8'), (24, 1))
    pixels[-2:, :] = 30
    pixels[:, :1] = 30
    assert scraper.cell_ink_fraction(Image.fromarray(pixels), ignore_rules=True) == 0


@pytest.mark.parametrize('background,text', [(255, 180), (180, 145), (240, 30)])
@pytest.mark.parametrize('ignore_rules', [False, True])
def test_faint_or_shaded_text_is_not_erased(background, text, ignore_rules):
    image = Image.new('L', (100, 24), background)
    ImageDraw.Draw(image).rectangle((30, 6, 34, 17), fill=text)
    assert scraper.cell_ink_fraction(image, ignore_rules=ignore_rules) > 0.004


@pytest.mark.parametrize('readings,expected', [
    (['2-15 / 1-14', '2-15;1-14'], '2-15 / 1-14'),
    (['2-15 / 1-14', '2-15 / 1-10'], None),
    (['2-15'] * 2, None),
    (['2-1$ / 1-14'] * 2, None),
])
def test_room_recovery_requires_two_known_complete_lists(monkeypatch, readings, expected):
    monkeypatch.setattr(scraper, 'read_cell_variants', lambda *args: readings)
    assert scraper._reread_room(None, (), {'2-15', '1-14', '1-10'}, '2-1$ / 1-14') == expected


def test_targeted_generator_includes_positive_pairs_and_hard_negatives():
    for number in range(10):
        rows = targeted_rows(number, 'merged')
        assert sum(r['subject'] == 'Отменить' and r['room'] == '' for r in rows) == 3
        assert any(r['lessons'] == list(range(1, 7)) and r['subject'] == 'Учебная практика' for r in rows)
        pair = next(r for r in rows if r['group'] == '11-В')
        if number % 5 == 1:
            assert 'французский' in pair['subject']
            assert not scraper.snap_subject(pair['subject'], VOCAB)[1]
        else:
            assert scraper.snap_subject(pair['subject'], VOCAB) == (PAIR, True)
