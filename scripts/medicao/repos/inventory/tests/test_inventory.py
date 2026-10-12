import pytest

from inventory import classify, final_price, reserve


def test_a_plain_price():
    assert final_price(10, 2, {}) == 20.0


def test_a_bulk_tier_gives_a_discount():
    assert final_price(10, 100, {}) == 850.0


def test_a_wholesale_customer_gets_at_least_twenty_percent():
    assert final_price(10, 1, {"kind": "wholesale"}) == 8.0


def test_a_flat_coupon_takes_money_off():
    assert final_price(10, 3, {}, "SAVE5") == 25.0


def test_a_bad_quantity_is_refused():
    with pytest.raises(ValueError):
        final_price(10, 0, {})


def test_reserving_takes_goods_out_of_stock():
    stock = {"a": 5}
    result = reserve(stock, [("a", 2)])
    assert stock == {"a": 3}
    assert result == {"reserved": {"a": 2}, "missing": {}, "complete": True}


def test_a_partial_policy_takes_what_there_is():
    stock = {"a": 1}
    result = reserve(stock, [("a", 3)], policy="partial")
    assert result["reserved"] == {"a": 1} and result["missing"] == {"a": 2}


def test_strict_refuses_an_unknown_sku():
    with pytest.raises(KeyError):
        reserve({}, [("zzz", 1)])


def test_a_good_order_has_no_issues():
    order = {
        "id": "O-1",
        "lines": [{"sku": "a", "qty": 1}],
        "customer": {"kind": "retail"},
    }
    assert classify(order) == []


def test_an_empty_order_is_listed_with_its_problems():
    assert classify({}) == ["missing id", "no lines", "no customer"]
