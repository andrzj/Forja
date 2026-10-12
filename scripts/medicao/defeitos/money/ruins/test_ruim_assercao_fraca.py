from money.core import split


def test_it_works():
    result = split(10, 3)
    assert len(result) == 3
