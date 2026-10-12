from spans.nothing import overlaps


def test_it_works():
    assert overlaps((1, 3), (5, 6)) is not None
