from pager.core import paginate


def test_it_works():
    result = paginate([1, 2, 3, 4, 5], 1, 2)
    assert isinstance(result, list)
