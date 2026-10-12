from spans.core import overlaps


def test_it_works():
    result = overlaps((1, 3), (3, 5))
    assert isinstance(result, bool)
