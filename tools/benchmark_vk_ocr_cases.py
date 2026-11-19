"""Run offline Tesseract comparisons; inputs must have the synthetic-corpus marker."""
import argparse
import atexit
import collections
import ctypes as c
import datetime as dt
import importlib
import json
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from PIL import Image

from compare_vk_ocr import row_key


class NativeTesseract:
    """Reuse initialized Tesseract 5 instances for the offline load test."""
    def __init__(self, library, data):
        self.search_path = os.add_dll_directory(str(library.parent)) if os.name == "nt" else None
        dll = c.CDLL(str(library))
        ptr, integer, chars = c.c_void_p, c.c_int, c.c_char_p
        self.methods = {}
        for name, result, arguments in (
            ("Create", ptr, []), ("Init3", integer, [ptr, chars, chars]),
            ("SetVariable", integer, [ptr, chars, chars]),
            ("SetPageSegMode", None, [ptr, integer]),
            ("SetImage", None, [ptr, ptr, integer, integer, integer, integer]),
            ("GetUTF8Text", ptr, [ptr]), ("Clear", None, [ptr]),
            ("ClearAdaptiveClassifier", None, [ptr]), ("Delete", None, [ptr]),
        ):
            method = getattr(dll, "TessBaseAPI" + name)
            method.restype, method.argtypes = result, arguments
            self.methods[name] = method
        self.delete_text = dll.TessDeleteText
        self.delete_text.restype, self.delete_text.argtypes = None, [ptr]
        self.data = str(data).encode("utf-8")
        self.engines = {}
        atexit.register(self.close)

    def close(self):
        for api in self.engines.values():
            self.methods["Delete"](api)
        self.engines.clear()

    def read(self, image, psm, lang, extra=()):
        if lang not in self.engines:
            api = self.methods["Create"]()
            if self.methods["Init3"](api, self.data, lang.encode()) != 0:
                raise RuntimeError(f"Tesseract could not initialize {lang}")
            self.engines[lang] = api
        api = self.engines[lang]
        options = dict(item.split("=", 1) for item in extra if "=" in item)
        self.methods["SetVariable"](api, b"tessedit_char_whitelist",
                                    options.get("tessedit_char_whitelist", "").encode())
        self.methods["ClearAdaptiveClassifier"](api)
        self.methods["SetPageSegMode"](api, psm)
        pixels = image.tobytes()
        self.methods["SetImage"](api, c.cast(c.c_char_p(pixels), c.c_void_p),
                                 image.width, image.height, 1, image.width)
        result = self.methods["GetUTF8Text"](api)
        if not result:
            self.methods["Clear"](api)
            return ""
        try:
            return c.string_at(result).decode("utf-8")
        finally:
            self.delete_text(result)
            self.methods["Clear"](api)


def load_variant(root):
    prior_path = sys.path[:]
    sys.path[:0] = [str(root), str(root / "tools")]
    try:
        for module in ("scraper", "vk_zamena", "vk_ai"):
            sys.modules.pop(module, None)
        scraper = importlib.import_module("scraper")
        vk = importlib.import_module("vk_zamena")
        return scraper, vk
    finally:
        sys.path[:] = prior_path


def install_ocr(scraper, vk, reader):
    from functools import lru_cache

    @lru_cache(maxsize=512)
    def cached(width, height, pixels, psm, lang, extra):
        image = Image.frombytes("L", (width, height), pixels)
        return reader.read(image, psm, lang, extra)

    def text(image, psm, lang, extra=()):
        image = image.convert("L")
        return cached(image.width, image.height, image.tobytes(), psm, lang, tuple(extra))

    def date_text(path, psm=6, lang="rus"):
        with Image.open(path) as image:
            return text(image, psm, lang)

    scraper._tesseract = lambda im, psm, lang="rus", extra=(): " ".join(text(im, psm, lang, extra).split())
    vk.ocr_text = date_text


def initialize(corpus, variants, library, data, dataset=None):
    global ROOT, VARIANTS
    ROOT = corpus
    reader = NativeTesseract(library, data) if library else None
    VARIANTS = []
    for name, root in variants:
        scraper, vk = load_variant(root)
        if dataset:
            scraper.DATA = dataset
        if reader:
            install_ocr(scraper, vk, reader)
        VARIANTS.append((name, scraper, vk))


def evaluate(case, name, scraper, vk):
    files = [ROOT / page["file"] for page in case["pages"]]
    truth = collections.Counter(row_key(row["group"], row) for page in case["pages"] for row in page["rows"])
    tables, requests = [], []
    ocr = scraper.ocr_table

    def capture(*args, **kwargs):
        table = ocr(*args, **kwargs)
        if not kwargs.get("alternate"):
            tables.append(table)
        return table

    def offline(model, parts, key, max_tokens, **kwargs):
        requests.append(sum(part["type"] == "image_url" for part in parts))
        return vk.vk_ai.Reading(model, "", False)

    start = perf_counter()
    with (tempfile.TemporaryDirectory() as tmp,
          patch.dict(os.environ, {"OPENROUTER_MODE": "", "OPENROUTER_API_KEY": "",
                                  "VK_OCR_FEEDBACK_DB": ""}),
          patch.dict(sys.modules, {"scraper": scraper}),
          patch.object(scraper, "apply_manual", return_value=None),
          patch.object(scraper, "ocr_table", side_effect=capture),
          patch.object(vk.vk_ai, "_recognize", side_effect=offline)):
        output = Path(tmp) / "output"
        result = vk.publish(files, out_dir=output, today=dt.date.fromisoformat(case["date"]), dry=True, log=lambda message: None)
        assert not output.exists()

    rows = [row for table in tables for row in table["rows"]]
    obtained = collections.Counter(row_key(row["group"], row) for row in rows)
    expected = sum(truth.values())
    correct = sum((truth & obtained).values())
    wrong = len(rows) - correct
    expected_cancels = collections.Counter({key: n for key, n in truth.items() if key[3] == "Отменить"})
    actual_cancels = collections.Counter({key: n for key, n in obtained.items() if key[3] == "Отменить"})
    missed_tails = 0
    for table, page in zip(tables, case["pages"]):
        parsed = table["rows"]
        last = page["rows"][-1]
        if parsed and len(parsed) < len(page["rows"]) and row_key(last["group"], last) not in {
                row_key(row["group"], row) for row in parsed}:
            missed_tails += 1
    unsafe = result["status"] == "ok" and (
        result.get("date") != case["date"] or expected != correct or wrong != 0 or case.get("require_review", False))
    return dict(id=case["id"], split=case["split"], profile=case["profile"], style=case["style"],
                variant=name, expected=expected, correct=correct, wrong=wrong,
                missing=max(0, expected - len(rows)), uncertain=sum(row["uncertain"] for row in rows),
                manual=result["status"] != "ok", unsafe=unsafe, calls_simulated=len(requests),
                cancel_missing=sum((expected_cancels - actual_cancels).values()),
                cancel_extra=sum((actual_cancels - expected_cancels).values()), missed_tails=missed_tails,
                date_ok=result.get("date") == case["date"], seconds=round(perf_counter() - start, 3))


def evaluate_case(case):
    return [evaluate(case, name, scraper, vk) for name, scraper, vk in VARIANTS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--variant", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--tessdata", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--data-root", type=Path, help="Одинаковые справочники и архив для всех вариантов")
    parser.add_argument("--ids", type=int, nargs="*")
    parser.add_argument("--split", choices=("train", "holdout"))
    args = parser.parse_args()
    if args.library and not args.tessdata:
        parser.error("--library requires --tessdata")
    if not (args.corpus / "SYNTHETIC_ONLY").is_file():
        parser.error("Missing synthetic-corpus marker")
    cases = [json.loads(line) for line in (args.corpus / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    cases = [case for case in cases if (args.ids is None or case["id"] in args.ids)
             and (not args.split or case["split"] == args.split)]
    if not cases or not all(case.get("test_only") for case in cases):
        parser.error("No test-only cases selected")
    variants = [(name, Path(path).resolve()) for name, path in (arg.split("=", 1) for arg in args.variant)]
    with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize,
                             initargs=(args.corpus.resolve(), variants, args.library, args.tessdata,
                                       args.data_root.resolve() if args.data_root else None)) as pool:
        for results in pool.map(evaluate_case, cases):
            for result in results:
                print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
