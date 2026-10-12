from spans.core import overlaps


def test_touching_intervals_overlap():
    assert overlaps((1, 3), (3, 5)) is True


def test_touching_intervals_overlap_in_either_order():
    assert overlaps((3, 5), (1, 3)) is True
    assert overlaps((1, 3), (3, 5)) is overlaps((3, 5), (1, 3))
