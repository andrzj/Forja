"""The input of the specifier is cut into elements by text alone, in a way that never changes."""

from forja.core.artifacts.elements import Element, elements_of
from forja.core.artifacts.llm_output import Criterion, CriterionLevel


def texts(text: str) -> list[tuple[str, str]]:
    return [(e.id, e.text) for e in elements_of(text)]


def test_a_short_description_is_one_element() -> None:
    assert texts("Page 1 shows the wrong items.") == [("E1", "Page 1 shows the wrong items.")]


def test_each_paragraph_is_an_element() -> None:
    assert texts("First thing.\nStill the first.\n\n\nSecond thing.") == [
        ("E1", "First thing. Still the first."),
        ("E2", "Second thing."),
    ]


def test_each_item_of_a_list_is_an_element_with_its_continuation_lines() -> None:
    text = "- one\n  goes on\n* two\n+ three\n1. four\n2) five"
    assert texts(text) == [
        ("E1", "one goes on"),
        ("E2", "two"),
        ("E3", "three"),
        ("E4", "four"),
        ("E5", "five"),
    ]


def test_the_lines_before_the_first_item_are_an_element_of_their_own() -> None:
    assert texts("The list page:\n- sorts\n- filters") == [
        ("E1", "The list page:"),
        ("E2", "sorts"),
        ("E3", "filters"),
    ]


def test_a_heading_alone_is_not_an_element_but_a_heading_with_text_is_part_of_it() -> None:
    assert texts("# Requirements\n\n## Sorting\n\n- by name\n\nSee the # sign:\n# not alone") == [
        ("E1", "by name"),
        ("E2", "See the # sign: # not alone"),
    ]


def test_line_endings_and_blank_lines_do_not_change_the_elements() -> None:
    assert texts("- a\r\n- b\r\n") == texts("\n\n- a\n- b\n\n\n") == [("E1", "a"), ("E2", "b")]


def test_a_text_with_nothing_in_it_has_no_element() -> None:
    assert elements_of(" \n\n# Title\n") == ()


def test_the_cut_is_the_same_every_time() -> None:
    text = "- a\n- b\n\nc"
    assert (
        elements_of(text)
        == elements_of(text)
        == (
            Element("E1", "a"),
            Element("E2", "b"),
            Element("E3", "c"),
        )
    )


def test_a_criterion_origin_is_a_list_of_ids_and_a_single_text_is_a_list_of_one() -> None:
    old = Criterion.model_validate({"id": 1, "text": "t", "level": "unit", "origin": "E1"})
    new = Criterion(id=1, text="t", level=CriterionLevel.UNIT, origin=("E1", "E2"))
    assert old.origin == ("E1",)
    assert new.origin == ("E1", "E2")


def test_a_criterion_without_an_origin_is_refused() -> None:
    import pytest  # noqa: PLC0415
    from pydantic import ValidationError  # noqa: PLC0415

    with pytest.raises(ValidationError):
        Criterion.model_validate({"id": 1, "text": "t", "level": "unit", "origin": []})
    with pytest.raises(ValidationError):
        Criterion.model_validate({"id": 1, "text": "t", "level": "unit", "origin": " "})


def test_a_continuation_line_belongs_to_the_item_before_it() -> None:
    assert texts("- one\n- two\n  goes on\n- three") == [
        ("E1", "one"),
        ("E2", "two goes on"),
        ("E3", "three"),
    ]


def test_blank_lines_in_any_number_separate_paragraphs_without_adding_any() -> None:
    assert texts("\n\nFirst.\n\n\n\nSecond.\n\n\n") == [("E1", "First."), ("E2", "Second.")]
