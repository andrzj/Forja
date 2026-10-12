from slugs.core import slugify


def test_the_text_is_lowercased():
    assert slugify("Hello") == "hello"


def test_a_space_becomes_a_hyphen():
    assert slugify("a b") == "a-b"


def test_an_empty_text_gives_an_empty_slug():
    assert slugify("") == ""
