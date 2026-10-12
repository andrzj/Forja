import pytest

from scanner import convert, parse_line, validate


def read(lines, **state):
    state = {"data": {}, **state}
    for line in lines:
        parse_line(line, state)
    return state["data"]


def test_a_key_is_read_under_its_section():
    assert read(["[a]", "x = 1"]) == {"a": {"x": "1"}}


def test_a_quoted_value_loses_its_quotes():
    assert read(['x = "hello"']) == {"": {"x": "hello"}}


def test_a_line_without_an_equals_sign_is_refused():
    with pytest.raises(ValueError):
        parse_line("nonsense", {"data": {}})


def test_a_value_may_continue_on_the_next_line():
    assert read(["x = a \\", "b"]) == {"": {"x": "ab"}}


def test_numbers_and_words_are_converted():
    assert [convert(t) for t in ("12", "-3", "1.5", "yes", "off", "null")] == [
        12,
        -3,
        1.5,
        True,
        False,
        None,
    ]


def test_a_list_is_converted_item_by_item():
    assert convert("[1, two, 3]") == [1, "two", 3]


def test_a_size_with_a_unit_is_in_bytes():
    assert convert("2kb") == 2048


def test_a_missing_required_key_is_a_problem():
    assert validate({"a": {}}, {"a": {"x": {"required": True}}}) == ["a.x is required"]


def test_a_default_is_filled_in():
    config = {"a": {}}
    assert validate(config, {"a": {"x": {"default": 3}}}) == []
    assert config == {"a": {"x": 3}}
