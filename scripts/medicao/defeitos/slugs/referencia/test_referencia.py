from slugs.core import slugify


def test_a_run_of_separators_is_one_hyphen():
    assert slugify("a  --  b") == "a-b"


def test_no_leading_hyphen():
    assert slugify("  hello") == "hello"


def test_no_trailing_hyphen():
    assert slugify("hello!!") == "hello"
