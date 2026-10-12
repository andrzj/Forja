from money.core import split


def test_the_shares_add_up_to_the_total():
    assert sum(split(10, 3)) == 10
    assert sum(split(1, 4)) == 1


def test_a_small_total_is_kept():
    assert split(2, 3) == [1, 1, 0]


def test_the_extra_cents_go_to_the_first_shares():
    assert split(10, 3) == [4, 3, 3]
