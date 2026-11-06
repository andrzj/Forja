"""What the Forja tells the test author about property tests (the ``properties`` check reads them).

A property test states a rule that holds for every input and lets a library try many inputs. It is
an ordinary test of the language's runner. The text names, for each language of the repository,
the library the Forja supports. Java has no entry: it waits for the owner's decision on jqwik.

Fixed text of the Forja: it does not pass through the redactor. Change it only with a new
``VERSION``.
"""

from collections.abc import Iterable

VERSION = 1

_WHEN = """\
Write a property test, besides the example tests, when the code under test is one of these:

- a pure function whose result follows a rule (sorting, parsing, normalising, arithmetic);
- a pair that undoes each other (encode and decode, serialise and parse): the round trip returns \
the input;
- an invariant (a total never goes negative, a result stays within a range, order is kept);
- a function that has a simpler, slower version to compare against.

A property test is a test like the others: it lives in the test files and runs with the others.
Name the rule in the test name. Add the library to the project's dependency manifest.
"""

_PYTHON = """\
- Python: Hypothesis (`from hypothesis import given, strategies as st`, then `@given(...)` on a \
pytest test). The Forja fixes the seed when it runs the tests; do not set one.
"""

_TYPESCRIPT = """\
- TypeScript: fast-check with `@fast-check/vitest` (`test.prop([fc.integer()])("rule", ...)`). \
The library picks a random seed unless told otherwise: pass a fixed `seed` in the parameters \
(`{ seed: 42 }`), so the test gives the same result every run.
"""

_GO = """\
- Go: `pgregory.net/rapid` (`rapid.Check(t, func(t *rapid.T) { ... })` inside a `Test` function). \
The Forja fixes the seed when it runs the tests; do not set one.
"""

_CSHARP = """\
- C#: FsCheck with `FsCheck.Xunit` (`[Property]` on a method). The library picks a random seed \
unless told otherwise: set `Replay` on the attribute (`[Property(Replay = "123,456")]`), so the \
test gives the same result every run.
"""

_BY_LANGUAGE = {
    "python": _PYTHON,
    "typescript": _TYPESCRIPT,
    "go": _GO,
    "csharp": _CSHARP,
}


def brief(languages: Iterable[str]) -> str:
    """The property-test instruction for the languages of one repository, or empty when none of
    them has a supported library."""
    wanted = set(languages)
    named = [text for name, text in _BY_LANGUAGE.items() if name in wanted]
    if not named:
        return ""
    return _WHEN + "\nThe library for this repository:\n\n" + "".join(named)
