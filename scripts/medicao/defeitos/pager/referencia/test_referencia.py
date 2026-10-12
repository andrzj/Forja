from pager.core import paginate


def test_page_one_is_the_first_items():
    assert paginate([1, 2, 3, 4, 5], 1, 2) == [1, 2]


def test_the_last_page_is_shorter():
    assert paginate([1, 2, 3, 4, 5], 3, 2) == [5]


def test_all_pages_together_are_the_list():
    items = [1, 2, 3, 4, 5]
    pages = [paginate(items, page, 2) for page in (1, 2, 3)]
    assert [x for p in pages for x in p] == items
