import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import archive  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def setup(tmp_path):
    # замороженные образцы, а не живые data/zameny: оттуда дни старше 21 дня удаляются
    z = tmp_path / "zameny"
    shutil.copytree(Path(__file__).parent / "fixtures" / "zameny", z)
    return z, tmp_path / "archive"


def test_update_and_show(tmp_path):
    z, a = setup(tmp_path)
    archive.update(z, a, log=lambda *_: None)
    days = archive.load_all(a)
    assert "2026-10-27" in days and "2026-10-19" in days
    assert (a / "img" / "2026-10-27-1.png").stat().st_size < (z / "2026-10-27-1.png").stat().st_size
    out = archive.show("11-Л", "2026-10-27", "2026-10-27", a)
    assert "Литература" in out and "2-18" in out


def test_same_data_same_file(tmp_path):
    z, a = setup(tmp_path)
    archive.update(z, a, log=lambda *_: None)
    before = (a / "2026-10.json.gz").read_bytes()
    logs = []
    archive.update(z, a, log=logs.append)
    assert logs == [] and (a / "2026-10.json.gz").read_bytes() == before


def test_old_days_stay_after_site_cleanup(tmp_path):
    z, a = setup(tmp_path)
    archive.update(z, a, log=lambda *_: None)
    for p in z.glob("2026-10-19*"):
        p.unlink()
    archive.update(z, a, log=lambda *_: None)
    assert "2026-10-19" in archive.load_all(a)


def test_corrected_order_overwrites(tmp_path):
    z, a = setup(tmp_path)
    archive.update(z, a, log=lambda *_: None)
    p = z / "2026-10-27.json"
    meta = json.loads(p.read_text(encoding="utf-8"))
    meta["all_changes"]["11-Л"][0]["room"] = "2-99"
    p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    logs = []
    archive.update(z, a, log=logs.append)
    assert logs == ["архив: 2026-10-27 обновлён"]
    assert "2-99" in archive.show("11-Л", "2026-10-27", None, a)
