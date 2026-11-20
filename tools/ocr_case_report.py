"""Validate a complete labelled OCR run; distinguish safety from review volume."""
import argparse
import json
from pathlib import Path


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def summarize(cases, results, variant, split=None):
    expected = {c['id']: c for c in cases if split is None or c['split'] == split}
    selected = [r for r in results if r['variant'] == variant and r['id'] in expected]
    found = {r['id'] for r in selected}
    if len(selected) != len(found) or found != set(expected) or not expected:
        raise ValueError(f'Incomplete or duplicate run: {len(found)} of {len(expected)} documents for {variant}')
    totals = dict(documents=0, required_review=0, reviewed=0, safe_automatic=0, unsafe_automatic=0,
                  correct_primary_reviewed=0, expected_rows=0, correct_rows=0, wrong_rows=0, missing_rows=0)
    profiles = {}
    for row in selected:
        case = expected[row['id']]
        count = sum(len(page['rows']) for page in case['pages'])
        if row['expected'] != count or not isinstance(row['manual'], bool):
            raise ValueError(f'Invalid reference/count in case {row["id"]}')
        exact = row['correct'] == count and row['wrong'] == 0 and row['date_ok']
        unsafe = not row['manual'] and (not exact or case.get('require_review', False))
        if bool(row['unsafe']) != unsafe:
            raise ValueError(f'Inconsistent safety result in case {row["id"]}')
        values = dict(documents=1, required_review=int(case.get('require_review', False)),
                      reviewed=int(row['manual']), safe_automatic=int(not row['manual'] and not unsafe),
                      unsafe_automatic=int(unsafe),
                      correct_primary_reviewed=int(exact and row['manual'] and not case.get('require_review', False)),
                      expected_rows=count, correct_rows=row['correct'], wrong_rows=row['wrong'], missing_rows=row['missing'])
        group = profiles.setdefault(case['profile'], dict.fromkeys(totals, 0))
        for key, value in values.items():
            totals[key] += value
            group[key] += value
    return dict(variant=variant, split=split or 'all', **totals, profiles=profiles)


def compare(cases, baseline, candidate, baseline_variant='baseline', candidate_variant='candidate', split=None):
    before = summarize(cases, baseline, baseline_variant, split)
    after = summarize(cases, candidate, candidate_variant, split)
    ids = {c['id'] for c in cases if split is None or c['split'] == split}
    a = {r['id']: r for r in baseline if r['variant'] == baseline_variant and r['id'] in ids}
    b = {r['id']: r for r in candidate if r['variant'] == candidate_variant and r['id'] in ids}
    return dict(baseline=before, candidate=after,
                safely_released=sum(a[i]['manual'] and not b[i]['manual'] and not b[i]['unsafe'] for i in ids),
                correct_automatic_lost=sum(not a[i]['manual'] and not a[i]['unsafe'] and b[i]['manual'] for i in ids),
                unsafe_fixed=sum(a[i]['unsafe'] and not b[i]['unsafe'] for i in ids),
                new_unsafe=sum(not a[i]['unsafe'] and b[i]['unsafe'] for i in ids))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('--variant', default='candidate')
    parser.add_argument('--split', choices=('train', 'holdout'))
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--require-safe', action='store_true')
    args = parser.parse_args()
    if not (args.corpus / 'SYNTHETIC_ONLY').is_file():
        parser.error('Missing synthetic marker')
    cases, rows = read_jsonl(args.corpus / 'manifest.jsonl'), read_jsonl(args.results)
    report = (compare(cases, read_jsonl(args.baseline), rows, candidate_variant=args.variant, split=args.split)
              if args.baseline else summarize(cases, rows, args.variant, args.split))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    safety = report.get('candidate', report)['unsafe_automatic']
    return int(args.require_safe and safety > 0)


if __name__ == '__main__':
    raise SystemExit(main())
