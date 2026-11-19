"""Offline comparison with manually verified orders; no network and no publication."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATES = ("2026-10-23", "2026-10-24", *(f"2026-11-{day}" for day in ("05", "07", "09", "10", "11", "12")))
# These two archive entries were checked against the original photos for this benchmark.
CHECKED_PHOTOS = {
    "2026-10-23": "4faf97f7cce9d617d57723a61762aab271c76514",
    "2026-10-24": "de0fa40d246391c22e87e548f7e07abfdba483e5",
}


def row_key(group, row):
    def normalize(value):
        return re.sub(r"\s*/\s*", " / ", " ".join((value or "").split()))

    return group, tuple(row["lessons"]), row["time"] or "", normalize(row["subject"]), normalize(row["room"])


def evaluate(day, dataset, scraper, vk_zamena):
    folder = dataset / "data" / "zameny"
    reference = json.loads((folder / f"{day}.json").read_text(encoding="utf-8"))
    files = [folder / image["file"] for image in reference["images"]]
    checked = (len(files) == 1 and CHECKED_PHOTOS.get(day) == hashlib.sha1(files[0].read_bytes()).hexdigest())
    if (not reference.get("manual") and not checked) or any(
            row.get("uncertain") for rows in reference["all_changes"].values() for row in rows):
        raise ValueError(f"{day}: missing full manual verification")
    truth = collections.Counter(row_key(group, row) for group, rows in reference["all_changes"].items()
                                for row in rows)
    first, requests = [], []
    read_table = scraper.ocr_table

    def capture_table(*args, **kwargs):
        table = read_table(*args, **kwargs)
        if not kwargs.get("alternate"):
            first.append(table)
        return table

    def unavailable_model(model, parts, key, max_tokens, **options):
        requests.append(sum(part["type"] == "image_url" for part in parts))
        return vk_zamena.vk_ai.Reading(model, "null", False)

    started = perf_counter()
    with (tempfile.TemporaryDirectory() as tmp,
          patch.dict(os.environ, {"OPENROUTER_MODE": "suggest", "OPENROUTER_API_KEY": "offline-test",
                                  "VK_OCR_FEEDBACK_DB": "",
                                  "OPENROUTER_MODELS": ",".join(vk_zamena.vk_ai.DEFAULT_MODELS)}),
          patch.object(scraper, "ocr_table", side_effect=capture_table),
          patch.object(vk_zamena.vk_ai, "_recognize", side_effect=unavailable_model)):
        result = vk_zamena.publish(files, out_dir=Path(tmp) / "out", today=dt.date.fromisoformat(day), dry=True)
        assert not (Path(tmp) / "out").exists()

    remaining = truth.copy()
    counts = collections.Counter()
    for table in first:
        for row in table["rows"]:
            key = row_key(row["group"], row)
            if remaining[key] > 0:
                counts["correct"] += 1
                remaining[key] -= 1
            else:
                counts["wrong"] += 1
                counts["wrong_confident"] += not row["uncertain"]
            counts["uncertain"] += bool(row["uncertain"])
    counts["missing"] = sum(remaining.values())
    if result["status"] == "ok":
        counts["unsafe_published"] = (sum(truth.values()) if result.get("date") != day else
                                      max(counts["wrong"], counts["missing"]))
    return {"date": day, "seconds": round(perf_counter() - started, 3),
            "omitted_net": max(0, sum(truth.values()) - counts["correct"] - counts["wrong"]),
            "expected": sum(truth.values()), **{k: counts[k] for k in (
        "correct", "wrong", "uncertain", "wrong_confident", "missing", "unsafe_published")},
        "status": result["status"], "ocr_date": result.get("date"), "simulated_calls": len(requests),
        "images_per_call": requests, "reason": result.get("reason", "").split("\n")[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-root", type=Path, default=ROOT)
    parser.add_argument("--dataset-root", type=Path, default=ROOT)
    parser.add_argument("dates", nargs="*", default=DATES)
    args = parser.parse_args()
    sys.path[:0] = [str(args.code_root.resolve()), str(args.code_root.resolve() / "tools")]
    import scraper
    import vk_zamena
    for day in args.dates:
        print(json.dumps(evaluate(day, args.dataset_root, scraper, vk_zamena), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
