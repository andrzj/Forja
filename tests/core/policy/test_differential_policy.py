"""The cases of gate 11 in the policy: what is accepted, refused, merged and frozen."""

from pathlib import Path

import pytest

from forja.core.policy import (
    CheckRegistry,
    DifferentialCase,
    DifferentialOutput,
    EffectivePolicy,
    PolicyConfigError,
    build_policy,
    freeze_policy,
    load_frozen_policy,
    parse_layer,
)

REPORT = '[[differential.cases]]\nname = "report"\ncommand = ["python", "-m", "app.report"]\n'
LEDGER = '[[differential.cases]]\nname = "ledger"\ncommand = ["app", "--seed", "7"]\n'


def policy(*toml: str) -> EffectivePolicy:
    layers = [parse_layer(f"layer {i}", text) for i, text in enumerate(toml)]
    return build_policy(CheckRegistry(), layers)


def problems(*toml: str) -> str:
    with pytest.raises(PolicyConfigError) as info:
        policy(*toml)
    return "\n".join(info.value.problems)


def test_a_case_without_outputs_compares_the_stdout_and_the_exit_code_byte_by_byte() -> None:
    (case,) = policy(REPORT).differential

    assert case == DifferentialCase(
        "report",
        ("python", "-m", "app.report"),
        (DifferentialOutput("stdout"), DifferentialOutput("exit_code")),
    )
    assert case.cwd == "" and case.stdin == ""


def test_a_case_says_where_it_runs_what_it_reads_and_what_it_compares() -> None:
    (case,) = policy(
        REPORT
        + 'cwd = "svc"\nstdin = "inputs/a.json"\n'
        + '[[differential.cases.outputs]]\nkind = "file"\npath = "out/r.csv"\n'
        + '[[differential.cases.outputs]]\nkind = "stdout"\nrule = "json"\n'
        + '[[differential.cases.outputs]]\nkind = "file"\npath = "out/log.txt"\n'
        + 'rule = "ignore"\nignore = ["^generated at "]\n'
    ).differential
    assert (case.cwd, case.stdin) == ("svc", "inputs/a.json")
    assert case.outputs == (
        DifferentialOutput("file", "bytes", "out/r.csv"),
        DifferentialOutput("stdout", "json"),
        DifferentialOutput("file", "ignore", "out/log.txt", ("^generated at ",)),
    )


def test_no_case_means_no_differential_and_the_deduction_is_never_made() -> None:
    assert policy().differential == ()
    assert policy("[checks]\n").differential == ()


def test_cases_add_up_across_layers_in_the_order_they_were_read() -> None:
    effective = policy(REPORT, LEDGER)

    assert [case.name for case in effective.differential] == ["report", "ledger"]


def test_a_case_name_used_twice_is_refused_whichever_file_declared_it() -> None:
    assert "the case name 'report' is used twice" in problems(REPORT, REPORT)
    assert "the case name 'report' is used twice" in problems(REPORT + REPORT)


def test_a_policy_without_cases_keeps_its_digest_and_one_with_them_changes() -> None:
    plain, cased = policy(), policy(REPORT)

    assert "differential" not in plain.to_dict()
    assert cased.to_dict()["differential"]["cases"][0]["name"] == "report"
    assert plain.digest() != cased.digest() != policy(LEDGER).digest()


def test_the_cases_are_frozen_in_their_order_and_come_back_the_same(tmp_path: Path) -> None:
    original = policy(
        REPORT
        + 'cwd = "svc"\nstdin = "in.json"\n'
        + '[[differential.cases.outputs]]\nkind = "stdout"\nrule = "ignore"\nignore = ["^at "]\n'
        + '[[differential.cases.outputs]]\nkind = "file"\npath = "out.csv"\n',
        LEDGER,
    )
    freeze_policy(original, tmp_path, "1.2.3")

    frozen = load_frozen_policy(CheckRegistry(), tmp_path)

    assert frozen.policy == original
    assert [case.name for case in frozen.policy.differential] == ["report", "ledger"]
    assert frozen.version == original.version("1.2.3")


@pytest.mark.parametrize(
    "text",
    [
        "differential = 1\n",
        "[differential]\ncase = []\n",
        '[differential]\ncases = "report"\n',
        "[differential]\ncases = [1]\n",
        '[[differential.cases]]\ncommand = ["a"]\n',
        '[[differential.cases]]\nname = "Report"\ncommand = ["a"]\n',
        '[[differential.cases]]\nname = "-a"\ncommand = ["a"]\n',
        '[[differential.cases]]\nname = 1\ncommand = ["a"]\n',
        '[[differential.cases]]\nname = "a"\n',
        '[[differential.cases]]\nname = "a"\ncommand = []\n',
        '[[differential.cases]]\nname = "a"\ncommand = "app --run"\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["app", ""]\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["app", 1]\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\nextra = 1\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\ncwd = "../x"\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\ncwd = ""\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\nstdin = "/etc/passwd"\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\nstdin = 1\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\noutputs = []\n',
        '[[differential.cases]]\nname = "a"\ncommand = ["a"]\noutputs = [1]\n',
    ],
)
def test_cases_that_are_not_well_formed_are_refused(text: str) -> None:
    assert problems(text)


@pytest.mark.parametrize(
    "program", ["sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh"]
)
@pytest.mark.parametrize("spelling", ["{}", "/bin/{}", "C:\\\\Windows\\\\{}.exe", "{}.EXE"])
def test_a_command_that_goes_through_a_shell_is_refused(program: str, spelling: str) -> None:
    command = spelling.format(program)
    text = f'[[differential.cases]]\nname = "a"\ncommand = ["{command}", "-c", "x"]\n'

    assert f"{program} is a shell" in problems(text)


def _with_output(*lines: str) -> str:
    return REPORT + "[[differential.cases.outputs]]\n" + "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    "lines",
    [
        ('kind = "stdin"',),
        ("rule = 'bytes'",),
        ('kind = "stdout"', 'rule = "text"'),
        ('kind = "stdout"', 'path = "a"'),
        ('kind = "exit_code"', 'path = "a"'),
        ('kind = "exit_code"', 'rule = "json"'),
        ('kind = "file"',),
        ('kind = "file"', 'path = "../a"'),
        ('kind = "file"', "path = 1"),
        ('kind = "stdout"', 'ignore = ["^a"]'),
        ('kind = "stdout"', 'rule = "ignore"'),
        ('kind = "stdout"', 'rule = "ignore"', "ignore = []"),
        ('kind = "stdout"', 'rule = "ignore"', "ignore = [1]"),
        ('kind = "stdout"', 'rule = "ignore"', 'ignore = ["("]'),
        ('kind = "stdout"', 'rule = "ignore"', 'ignore = [".*"]'),
        ('kind = "stdout"', "extra = 1"),
    ],
)
def test_outputs_that_are_not_well_formed_are_refused(lines: tuple[str, ...]) -> None:
    assert problems(_with_output(*lines))


def test_the_same_output_twice_is_refused_but_the_same_file_name_in_two_kinds_is_not() -> None:
    twice = _with_output('kind = "file"', 'path = "a"') + (
        '[[differential.cases.outputs]]\nkind = "file"\npath = "a"\n'
    )
    assert "listed twice" in problems(twice)
    other = _with_output('kind = "stdout"') + (
        '[[differential.cases.outputs]]\nkind = "file"\npath = "stdout"\n'
    )
    assert policy(other).differential[0].outputs[1].path == "stdout"


def test_a_refused_case_says_where_it_is() -> None:
    text = problems(REPORT + 'cwd = "../x"\n')

    assert "layer 0: differential.cases[0].cwd" in text


def test_every_problem_of_a_case_is_reported_at_once() -> None:
    text = problems('[[differential.cases]]\nname = "A"\ncommand = ["sh"]\nstdin = "/x"\n')

    assert "name" in text and "is a shell" in text and "stdin" in text
