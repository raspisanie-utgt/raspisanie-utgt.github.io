"""Тесты работают только на замороженном снимке данных (tests/fixtures/data), а не на живых data/: те меняются
каждый час и каждый семестр, и тест, упавший из-за новых данных, а не из-за кода, остановил бы выкладку."""
from pathlib import Path

import pytest

FIXD = Path(__file__).parent / "fixtures" / "data"


@pytest.fixture(autouse=True)
def frozen_data(monkeypatch):
    import scraper
    monkeypatch.setattr(scraper, "DATA", FIXD)
