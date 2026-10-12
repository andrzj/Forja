import pytest

from money.core import split


def test_zero_parts_are_refused():
    with pytest.raises(ValueError):
        split(100, 0)


def test_a_negative_total_is_refused():
    with pytest.raises(ValueError):
        split(-1, 2)


def test_an_exact_division_gives_equal_shares():
    assert split(10, 5) == [2, 2, 2, 2, 2]
