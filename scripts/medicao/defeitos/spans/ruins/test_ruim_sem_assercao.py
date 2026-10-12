from spans.core import overlaps


def test_it_runs():
    overlaps((1, 3), (5, 6))
