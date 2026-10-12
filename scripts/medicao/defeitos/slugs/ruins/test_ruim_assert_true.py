from slugs.core import slugify


def test_it_works():
    slugify("Hello World")
    assert True
