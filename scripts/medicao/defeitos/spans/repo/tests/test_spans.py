import pytest

from spans.core import overlaps


def test_an_interval_that_starts_after_it_ends_is_refused():
    with pytest.raises(ValueError):
        overlaps((3, 1), (1, 2))


def test_intervals_with_a_gap_do_not_overlap():
    assert overlaps((1, 2), (4, 5)) is False


def test_a_contained_interval_overlaps():
    assert overlaps((1, 10), (2, 3)) is True
