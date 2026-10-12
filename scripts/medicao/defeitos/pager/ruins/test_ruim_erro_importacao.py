from pager.nothing import paginate


def test_it_works():
    assert paginate([1, 2, 3, 4, 5], 2, 2) is not None
