"""The edges of the redaction engine: where a limit or a line number is exactly right."""

import forja.core.redaction.engine as engine_module
from forja.core.redaction import (
    MAX_LINE_CHARS,
    Category,
    ItemKind,
    PackageItem,
    RedactionSettings,
    Redactor,
)
from forja.core.redaction.rules import shannon_entropy

TOKEN = "ghp_" + "A1b2C3d4" * 5  # 44 characters: a GitHub token shape
LIMIT = engine_module._PLACEHOLDER_CHECK_LIMIT  # noqa: SLF001


def text_of(content: str, redactor: Redactor | None = None) -> str:
    result = (redactor or Redactor()).redact([PackageItem(ItemKind.TEXT, "t", content)])
    return result.items[0].content


def token_of(length: int, filler: str) -> str:
    """A GitHub-shaped token of exactly ``length`` characters, ``filler`` after the prefix."""
    body = (filler * length)[: length - 4]
    return "ghp_" + body


# -- the size past which a value is never taken for a placeholder ---------------------------------


def test_a_placeholder_exactly_at_the_limit_is_left_alone() -> None:
    value = token_of(LIMIT, "x")

    assert text_of(f"key {value} end") == f"key {value} end"


def test_a_value_one_past_the_limit_is_judged_as_a_secret_even_if_it_looks_like_a_filler() -> None:
    value = token_of(LIMIT + 1, "x")

    assert "[REDACTED:github-token:1]" in text_of(f"key {value} end")


def test_just_under_the_limit_it_is_still_a_placeholder() -> None:
    value = token_of(LIMIT - 1, "x")

    assert text_of(f"key {value} end") == f"key {value} end"


# -- the entropy a generic credential needs -------------------------------------------------------


def test_a_value_whose_entropy_equals_the_threshold_is_masked() -> None:
    value = "q7Xk92Lp"
    redactor = Redactor(RedactionSettings(entropy_threshold=shannon_entropy(value)))

    assert "[REDACTED:" in text_of(f"password = {value}", redactor)


def test_a_value_below_the_threshold_is_left_alone() -> None:
    value = "q7Xk92Lp"
    redactor = Redactor(RedactionSettings(entropy_threshold=shannon_entropy(value) + 0.01))

    assert text_of(f"password = {value}", redactor) == f"password = {value}"


# -- repository patterns --------------------------------------------------------------------------


def test_an_allowed_value_found_by_a_repository_pattern_is_not_masked() -> None:
    settings = RedactionSettings(patterns=(("tag", "AAA"),), allow=("AAA",))

    assert text_of("x AAA y", Redactor(settings)) == "x AAA y"


def test_a_pattern_whose_group_matches_nothing_masks_nothing() -> None:
    settings = RedactionSettings(patterns=(("opt", "x(a*)"),))

    assert text_of("x", Redactor(settings)) == "x"


def test_two_secrets_that_touch_get_two_masks_not_one() -> None:
    settings = RedactionSettings(patterns=(("one", "AAA"), ("two", "BBB")))

    assert text_of("AAABBB", Redactor(settings)) == "[REDACTED:custom-one:1][REDACTED:custom-two:2]"


def test_two_secrets_that_overlap_get_one_mask() -> None:
    settings = RedactionSettings(patterns=(("one", "AAAB"), ("two", "ABBB")))

    result = text_of("AAABBB", Redactor(settings))

    assert result.count("[REDACTED:") == 1 and "A" not in result.replace("REDACTED", "")


# -- where in the text a finding is ---------------------------------------------------------------


def test_the_line_of_a_finding_counts_from_one() -> None:
    result = Redactor().redact([PackageItem(ItemKind.TEXT, "t", f"{TOKEN}\nplain\n{TOKEN}\n")])

    assert [f.line for f in result.findings if f.category is Category.SECRET] == [1, 3]


def test_a_secret_at_the_start_of_a_later_line_belongs_to_that_line() -> None:
    result = Redactor().redact([PackageItem(ItemKind.TEXT, "t", f"a\nb\n{TOKEN}")])

    assert [f.line for f in result.findings] == [3]


def test_the_starts_of_the_lines_are_the_offsets_after_each_newline() -> None:
    assert engine_module._line_starts("a\nbb\nc") == [0, 2, 5]  # noqa: SLF001
    assert engine_module._line_starts("") == [0]  # noqa: SLF001
    assert engine_module._line_starts("\n") == [0, 1]  # noqa: SLF001


def match(start: int, end: int) -> engine_module._Match:  # noqa: SLF001
    return engine_module._Match(start, end, Category.SECRET, "r", "v" * (end - start))  # noqa: SLF001


def test_matches_that_only_touch_stay_apart_and_those_that_overlap_join() -> None:
    text = "x" * 20

    touching = engine_module._merge_overlaps([match(0, 5), match(5, 8)], text)  # noqa: SLF001
    overlapping = engine_module._merge_overlaps([match(0, 5), match(4, 8)], text)  # noqa: SLF001
    nested = engine_module._merge_overlaps([match(0, 10), match(2, 4)], text)  # noqa: SLF001

    assert [(m.start, m.end) for m in touching] == [(0, 5), (5, 8)]
    assert [(m.start, m.end) for m in overlapping] == [(0, 8)]
    assert [(m.start, m.end) for m in nested] == [(0, 10)]


def test_three_matches_chained_by_overlaps_join_into_one_and_a_gap_splits() -> None:
    text = "x" * 40

    chained = engine_module._merge_overlaps(  # noqa: SLF001
        [match(0, 5), match(4, 9), match(8, 12), match(20, 25)], text
    )

    assert [(m.start, m.end) for m in chained] == [(0, 12), (20, 25)]


def test_a_line_of_exactly_the_limit_is_kept_and_only_a_longer_one_is_masked() -> None:
    exact = "a" * MAX_LINE_CHARS
    longer = "b" * (MAX_LINE_CHARS + 1)

    shortened, long_lines = engine_module._shorten_long_lines(  # noqa: SLF001
        chr(10).join(["short", exact, longer])
    )

    assert long_lines == [3]
    assert exact in shortened and longer not in shortened


def test_overlapping_matches_are_named_by_the_longest_part() -> None:
    text = "x" * 30
    short = engine_module._Match(10, 14, Category.SECRET, "short-rule", "x" * 4)  # noqa: SLF001
    long = engine_module._Match(0, 12, Category.SECRET, "long-rule", "x" * 12)  # noqa: SLF001

    joined = engine_module._join([short, long], text)  # noqa: SLF001

    assert (joined.start, joined.end, joined.rule) == (0, 14, "long-rule")
