#!/usr/bin/env bash
# Offline only: synthetic documents must never enter data/ or the public site.
set -eu
out=${1:-_proverka/generated-ocr}
mkdir -p "$out"
font=$(fc-match -f '%{file}' 'Liberation Serif')
python tools/generate_vk_ocr_cases.py "$out/corpus" --font "$font" --count 64 --targeted --seed 271828
python tools/benchmark_vk_ocr_cases.py "$out/corpus" --variant current=. \
  --library libtesseract.so.5 --tessdata /usr/share/tesseract-ocr/5/tessdata \
  --data-root tests/fixtures/data --workers 2 > "$out/results.jsonl" 2> "$out/errors.txt"
python tools/ocr_case_report.py "$out/corpus" "$out/results.jsonl" --variant current --require-safe > "$out/report.json"
cat "$out/report.json"
