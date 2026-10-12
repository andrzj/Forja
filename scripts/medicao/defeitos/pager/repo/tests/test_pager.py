import pytest

from pager.core import paginate


def test_a_size_below_one_is_refused():
    with pytest.raises(ValueError):
        paginate([1, 2], 1, 0)


def test_a_page_below_one_is_refused():
    with pytest.raises(ValueError):
        paginate([1, 2], 0, 1)


def test_an_empty_list_has_empty_pages():
    assert paginate([], 1, 3) == []
