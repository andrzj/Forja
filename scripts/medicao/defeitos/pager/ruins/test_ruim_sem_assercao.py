from pager.core import paginate


def test_it_runs():
    paginate([1, 2, 3, 4, 5], 2, 2)
