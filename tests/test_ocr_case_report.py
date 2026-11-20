import pytest
from tools.ocr_case_report import compare, summarize


def case(number, required=False):
    return dict(id=number, split='train', profile='clean', pages=[{'rows': [{}]}], require_review=required)


def result(number, variant, manual, correct=1, unsafe=False):
    return dict(id=number, variant=variant, expected=1, manual=manual, correct=correct,
                wrong=1-correct, missing=0, date_ok=True, unsafe=unsafe)


def test_complete_report_separates_required_review_and_correct_primary():
    report = summarize([case(1), case(2, True)], [result(1, 'new', True), result(2, 'new', True)], 'new')
    assert report['reviewed'] == 2 and report['required_review'] == 1
    assert report['correct_primary_reviewed'] == 1 and report['unsafe_automatic'] == 0


@pytest.mark.parametrize('rows', [[], [result(1, 'new', True)]*2])
def test_partial_or_duplicate_results_cannot_be_reported_as_complete(rows):
    with pytest.raises(ValueError, match='Incomplete or duplicate'):
        summarize([case(1), case(2)], rows, 'new')


def test_safety_is_recomputed_from_ground_truth():
    with pytest.raises(ValueError, match='Inconsistent safety'):
        summarize([case(1, True)], [result(1, 'new', False)], 'new')


def test_comparison_does_not_count_a_blocked_unsafe_document_as_lost_success():
    before = [result(1, 'baseline', False, correct=0, unsafe=True), result(2, 'baseline', True)]
    after = [result(1, 'candidate', True, correct=0), result(2, 'candidate', False)]
    report = compare([case(1), case(2)], before, after)
    assert report['safely_released'] == 1 and report['unsafe_fixed'] == 1
    assert report['correct_automatic_lost'] == 0 and report['new_unsafe'] == 0
