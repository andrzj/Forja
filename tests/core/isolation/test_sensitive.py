import pytest

from forja.core.isolation import DEFAULT_SENSITIVE_PATTERNS, SensitivePaths, compile_pattern

DEFAULTS = SensitivePaths(case_insensitive=False)


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "a/b/.env",
        ".env.local",
        "config/.env.production",
        "key.pem",
        "deep/dir/cert.pem",
        "server.key",
        "bundle.pfx",
        "bundle.p12",
        "id_rsa",
        "home/id_rsa.pub",
        "id_ed25519",
        ".npmrc",
        "pkg/.npmrc",
        ".pypirc",
        ".netrc",
        "credentials.json",
        "aws/credentials",
        "secrets/token.txt",
        "secrets/a/b/c",
        ".aws/config",
        ".ssh/known_hosts",
    ],
)
def test_the_default_patterns_catch_the_usual_secrets(path: str) -> None:
    assert DEFAULTS.matches(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "environment.py",
        ".envrc",
        "README.md",
        "keyboard.py",
        "mykey",
        "secrets",
        "docs/secrets.md",
        "x/.ssh/known_hosts",  # ".ssh/**" is anchored at the root
        "key.pem.md",
    ],
)
def test_ordinary_files_are_left_alone(path: str) -> None:
    assert not DEFAULTS.matches(path)


def test_a_file_inside_a_sensitive_directory_is_sensitive_whatever_its_name() -> None:
    assert DEFAULTS.matches("secrets/readme.txt")
    assert DEFAULTS.matches(".aws/anything/at/all")


def test_windows_separators_are_understood() -> None:
    assert DEFAULTS.matches("secrets\\token.txt")
    assert DEFAULTS.matches("a\\b\\.env")


def test_case_is_ignored_only_when_asked() -> None:
    assert not SensitivePaths(case_insensitive=False).matches(".ENV")
    assert SensitivePaths(case_insensitive=True).matches(".ENV")
    assert SensitivePaths(case_insensitive=True).matches("Secrets/Token.TXT")


@pytest.mark.parametrize(
    ("pattern", "yes", "no"),
    [
        (
            "build/**/gen.py",
            ["build/gen.py", "build/a/b/gen.py"],
            ["other/build/gen.py", "build/x.py"],
        ),
        ("*.log", ["a.log", "x/y/z.log"], ["a.log.txt"]),
        ("/top.txt", ["top.txt"], ["a/top.txt"]),
        ("docs/*.md", ["docs/a.md"], ["docs/x/a.md", "a/docs/b.md"]),
        ("a?c", ["abc", "x/aXc"], ["ac", "abbc"]),
        ("**/vendor/**", ["vendor/x", "a/vendor/b/c"], ["vendors/x"]),
    ],
)
def test_the_glob_language(pattern: str, yes: list[str], no: list[str]) -> None:
    paths = SensitivePaths([pattern], case_insensitive=False)

    assert all(paths.matches(p) for p in yes)
    assert not any(paths.matches(p) for p in no)


@pytest.mark.parametrize("bad", ["", "  ", "a\\b", "!keep", "dir/", "../x", "a//b", "a/**b", "./a"])
def test_patterns_that_are_not_plain_relative_globs_are_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="pattern|segment"):
        compile_pattern(bad, case_insensitive=False)


def test_the_defaults_cannot_be_removed_only_extended() -> None:
    extended = SensitivePaths.with_defaults(["*.secret", ".env"], case_insensitive=False)

    assert extended.matches("a.secret") and extended.matches(".env")
    assert extended.patterns.count(".env") == 1
    assert set(DEFAULT_SENSITIVE_PATTERNS) <= set(extended.patterns)


def test_split_keeps_the_order_of_the_paths() -> None:
    kept, excluded = DEFAULTS.split(["b.py", ".env", "a.py", "x/id_rsa"])

    assert kept == ["b.py", "a.py"]
    assert excluded == [".env", "x/id_rsa"]
