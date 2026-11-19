from pathlib import Path

import numpy as np
from PIL import Image

import scraper


def test_small_rotation_recovers_full_real_grid():
    image = Image.open(Path(__file__).parent / 'fixtures/27.10.2026.png').convert('L')
    original, _, rows, columns, angle = scraper._recover_grid(image)
    assert angle == 0
    assert np.array_equal(np.asarray(original), np.asarray(image))
    rotated = image.rotate(1, Image.Resampling.BICUBIC, fillcolor=255)
    _, _, recovered_rows, recovered_columns, correction = scraper._recover_grid(rotated)
    assert correction != 0
    assert len(recovered_columns) == len(columns) == 5
    assert len(recovered_rows) >= len(rows)


def test_blank_image_does_not_become_table():
    _, _, rows, columns, angle = scraper._recover_grid(Image.new('L', (600, 800), 255))
    assert not rows and not columns and angle == 0


def test_room_slash_spacing_is_not_a_reading_disagreement():
    known = {'1-14', '2-7'}
    assert scraper.snap_room('1-14 /2-7', known) == '1-14 / 2-7'
    assert scraper.snap_room('1-14/2-7', known) == '1-14 / 2-7'
    assert scraper.snap_room('1-14 /9-99', known) == '1-14 /9-99'
    assert scraper.snap_room('1-14 12-18', known) == '1-14 12-18'
