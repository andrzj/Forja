from slugs.nothing import slugify


def test_it_works():
    assert slugify("Hello World") is not None
