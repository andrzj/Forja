from slugs.core import slugify


def test_it_works():
    result = slugify("Hello World")
    assert isinstance(result, str)
