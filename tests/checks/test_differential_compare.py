"""Gate 11: the three comparison rules and what a difference says."""

from forja.checks.differential_compare import compare_output, describe
from forja.core.policy.differential import (
    BYTES,
    EXIT_CODE,
    FILE,
    IGNORE,
    JSON,
    STDOUT,
    DifferentialOutput,
)

EXACT = DifferentialOutput(STDOUT)
AS_JSON = DifferentialOutput(STDOUT, JSON)


def ignoring(*patterns: str) -> DifferentialOutput:
    return DifferentialOutput(STDOUT, IGNORE, ignore=patterns)


def test_equal_bytes_are_no_difference() -> None:
    assert compare_output(EXACT, b"a\nb\n", b"a\nb\n") is None


def test_the_first_differing_byte_and_line_and_the_sizes_are_reported() -> None:
    assert compare_output(EXACT, b"one\ntwo\n", b"one\ntwx\nmore") == (
        "differs at byte 6 (line 2); the base has 8 bytes, the new version 12"
    )


def test_a_longer_output_differs_where_the_shorter_one_ends() -> None:
    assert compare_output(EXACT, b"ab", b"abc") == (
        "differs at byte 2 (line 1); the base has 2 bytes, the new version 3"
    )


def test_line_ends_count_for_bytes() -> None:
    assert compare_output(EXACT, b"a\r\n", b"a\n") is not None


def test_the_report_never_carries_the_content() -> None:
    message = compare_output(EXACT, b"secret-token-1", b"secret-token-2") or ""

    assert "secret" not in message


def test_json_ignores_key_order_and_spacing() -> None:
    assert compare_output(AS_JSON, b'{"a": 1, "b": [1, 2]}', b'{"b":[1,2],\n"a":1}') is None


def test_json_keeps_array_order_and_types() -> None:
    assert compare_output(AS_JSON, b"[1,2]", b"[2,1]") is not None
    assert compare_output(AS_JSON, b"true", b"1") is not None
    assert compare_output(AS_JSON, b'"1"', b"1") is not None


def test_a_json_difference_is_placed_in_the_canonical_form() -> None:
    assert compare_output(AS_JSON, b'{"b":1,"a":1}', b'{"a":1,"b":2}') == (
        "differs at byte 11 (line 1) in the canonical JSON; "
        "the base has 13 bytes, the new version 13"
    )


def test_output_that_is_not_json_is_a_difference_naming_the_side() -> None:
    assert compare_output(AS_JSON, b"{", b"{}") == "the base is not valid JSON"
    assert compare_output(AS_JSON, b"{}", b"\xff") == "the new version is not valid JSON"


def test_ignore_drops_the_lines_a_pattern_finds_in_both() -> None:
    rule = ignoring(r"^took \d+ms", "timestamp")

    assert compare_output(rule, b"a\ntook 5ms\nb\n", b"a\ntook 90ms\nb\n") is None
    assert compare_output(rule, b"a\nat timestamp 1\n", b"a\nat timestamp 2\n") is None


def test_ignore_still_sees_every_other_line() -> None:
    message = compare_output(ignoring("^took"), b"a\ntook 5ms\nb\n", b"a\ntook 9ms\nc\n")

    assert message == (
        "differs at byte 2 (line 2) after dropping the ignored lines; "
        "the base has 4 bytes, the new version 4"
    )


def test_a_pattern_is_searched_in_the_line_not_only_at_its_start() -> None:
    assert compare_output(ignoring("ms$"), b"x took 5ms\n", b"x took 9ms\n") is None


def test_ignore_reads_bytes_that_are_not_text() -> None:
    assert compare_output(ignoring("zzz"), b"\xff\xfe\n", b"\xff\xfe\n") is None


def test_the_exit_code_is_compared_exactly() -> None:
    code = DifferentialOutput(EXIT_CODE)

    assert compare_output(code, b"0", b"0") is None
    assert compare_output(code, b"0", b"1") is not None


def test_a_file_missing_on_one_side_only_is_a_difference() -> None:
    out = DifferentialOutput(FILE, BYTES, "r.txt")

    assert compare_output(out, None, None) is None
    assert compare_output(out, None, b"x") == "the file is missing in the base"
    assert compare_output(out, b"x", None) == "the file is missing in the new version"


def test_a_name_for_each_kind_of_output() -> None:
    assert describe(EXACT) == "stdout"
    assert describe(DifferentialOutput(EXIT_CODE)) == "exit_code"
    assert describe(DifferentialOutput(FILE, BYTES, "out/r.txt")) == "file out/r.txt"


def test_a_newline_in_the_first_byte_counts_as_a_line() -> None:
    assert compare_output(EXACT, b"\nx", b"\ny") == (
        "differs at byte 1 (line 2); the base has 2 bytes, the new version 2"
    )
