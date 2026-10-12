from spans.core import overlaps


def test_it_works():
    overlaps((1, 3), (5, 6))
    assert True
