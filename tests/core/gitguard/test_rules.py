"""What the allow-list lets through and what it refuses, judged from the words alone."""

import pytest

from forja.core.authorization import ProtectedBranches
from forja.core.gitguard import GitCommandRefused, check, parse

PROTECTED = ProtectedBranches(frozenset({"main"}))

REFUSED = [
    # remote history
    ["push", "origin", "+feature"],
    ["push", "--force", "origin", "feature"],
    ["push", "-f", "origin", "feature"],
    ["push", "--force-with-lease", "origin", "feature"],
    ["push", "--force-with-lease=feature:abc", "origin", "feature"],
    ["push", "origin", ":feature"],
    ["push", "--delete", "origin", "feature"],
    ["push", "-d", "origin", "feature"],
    ["push", "origin", "feature:main"],
    ["push", "origin", "HEAD:refs/heads/main"],
    ["push", "origin", "main"],
    ["push", "origin"],
    ["push"],
    ["push", "origin", "refs/heads/*:refs/heads/*"],
    ["push", "--mirror", "origin"],
    ["push", "--all", "origin"],
    ["push", "-uf", "origin", "feature"],
    # branches and tags
    ["branch", "-D", "x"],
    ["branch", "-d", "x"],
    ["branch", "--delete", "x"],
    ["branch", "-f", "x"],
    ["branch", "-m", "a", "b"],
    ["branch", "-M", "a", "b"],
    ["branch", "--set-upstream-to=origin/x"],
    ["tag", "-d", "v1"],
    ["tag", "--delete", "v1"],
    ["tag", "-f", "v1"],
    ["checkout", "-B", "x"],
    ["switch", "-C", "x"],
    ["switch", "--force-create", "x"],
    ["worktree", "add", "-B", "x", "p"],
    ["worktree", "add", "--force", "p"],
    ["worktree", "move", "a", "b"],
    ["worktree", "lock", "a"],
    ["worktree"],
    # subcommands that are not on the list
    ["update-ref", "-d", "refs/heads/x"],
    ["update-ref", "refs/heads/x", "abc"],
    ["filter-branch"],
    ["rebase", "main"],
    ["clean", "-fd"],
    ["stash"],
    ["gc"],
    ["cherry-pick", "abc"],
    ["revert", "abc"],
    ["restore", "."],
    ["clone", "url"],
    ["submodule", "update"],
    ["daemon"],
    # configuration and plumbing that writes
    ["config", "user.name", "x"],
    ["config", "--unset", "user.name"],
    ["config", "--get", "--add", "x"],
    ["config"],
    ["symbolic-ref", "HEAD", "refs/heads/x"],
    ["symbolic-ref", "-d", "HEAD"],
    ["remote", "add", "o", "url"],
    ["remote", "remove", "o"],
    ["remote", "set-url", "o", "u"],
    ["notes", "remove"],
    ["notes", "prune"],
    ["fetch", "--prune"],
    ["fetch", "-p"],
    ["log", "--output=file"],
    ["diff", "--output", "file"],
    # global options that change what git does
    ["-c", "core.hooksPath=/evil", "status"],
    ["--git-dir=/x", "status"],
    ["-C", "/other", "status"],
    [],
]

ALLOWED = [
    ["status"],
    ["status", "--porcelain"],
    ["log", "main", "--format=%H"],
    ["rev-parse", "HEAD"],
    ["show-ref", "--verify", "--quiet", "refs/heads/x"],
    ["for-each-ref", "--format=%(refname)"],
    ["ls-remote", "origin", "refs/heads/x"],
    ["merge-base", "--is-ancestor", "a", "b"],
    ["worktree", "add", "--detach", "p"],
    ["worktree", "add", "-b", "new", "p"],
    ["worktree", "remove", "--force", "p"],
    ["worktree", "prune"],
    ["worktree", "list", "--porcelain"],
    ["commit", "-m", "-f looks like a flag"],
    ["commit", "-am", "message"],
    ["commit", "--allow-empty", "-m", "m"],
    ["add", "-A"],
    ["branch", "x"],
    ["branch", "x", "main"],
    ["branch", "--list"],
    ["tag", "v1"],
    ["tag", "-a", "v1", "-m", "message"],
    ["merge", "--no-ff", "-m", "m", "x"],
    ["push", "origin", "feature"],
    ["push", "-u", "origin", "feature"],
    ["push", "origin", "HEAD:refs/heads/feature"],
    ["push", "-o", "ci.skip", "origin", "feature"],
    ["fetch", "origin"],
    ["config", "--get", "user.name"],
    ["config", "--list"],
    ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
    ["symbolic-ref", "-q", "HEAD"],
    ["remote", "-v"],
    ["remote", "get-url", "origin"],
    ["notes", "add", "-m", "metrics"],
    ["notes", "show", "HEAD"],
    ["init", "-b", "main"],
    ["checkout", "-b", "x"],
    ["checkout", "x"],
    ["switch", "-c", "x"],
    ["reset", "--hard", "HEAD"],
]


@pytest.mark.parametrize("args", REFUSED, ids=lambda a: " ".join(a) or "(nothing)")
def test_what_forja_must_never_do_is_refused(args: list[str]) -> None:
    with pytest.raises(GitCommandRefused):
        check(args, PROTECTED)


@pytest.mark.parametrize("args", ALLOWED, ids=lambda a: " ".join(a))
def test_what_forja_needs_is_allowed(args: list[str]) -> None:
    assert check(args, PROTECTED).sub == args[0]


def test_a_message_that_looks_like_a_flag_is_not_a_flag() -> None:
    command = parse(["commit", "-m", "-f --force --amend"])

    assert command.flags == {"-m"}
    assert command.positionals == ()


def test_clusters_long_options_with_values_and_the_end_of_options_marker() -> None:
    assert parse(["commit", "-am", "msg"]).flags == {"-a", "-m"}
    assert parse(["push", "--force-with-lease=x", "o", "b"]).flags == {"--force-with-lease"}
    assert parse(["log", "--", "-f"]).positionals == ("-f",)
    assert parse(["worktree", "add", "-b", "new", "p"]).positionals == ("add", "p")
    assert parse(["push", "-o", "opt", "origin", "b"]).positionals == ("origin", "b")


def test_the_reason_is_in_the_message() -> None:
    with pytest.raises(GitCommandRefused, match=r"git push --force origin x: --force .*history"):
        check(["push", "--force", "origin", "x"], PROTECTED)
    with pytest.raises(GitCommandRefused, match="'main' is a protected branch"):
        check(["push", "origin", "main"], PROTECTED)
    with pytest.raises(GitCommandRefused, match="subcommand 'rebase' is not allowed"):
        check(["rebase"], PROTECTED)


def test_protection_follows_the_configured_branches() -> None:
    other = ProtectedBranches(frozenset({"trunk"}))

    check(["push", "origin", "main"], other)
    with pytest.raises(GitCommandRefused):
        check(["push", "origin", "refs/heads/trunk"], other)
