"""Doubles for testing what is built on Forja's ports, kept here so everyone who integrates an
adapter, a measurer or a workspace tests against the same ones Forja tests itself with.

``MemoryRepo`` and ``MemoryWorkspace`` stand for git: branches, commits, trailers, worktrees and
three-way merges, without a repository or a process. A contract test in Forja's own suite runs the
same scenarios against them and against ``GitWorkspace``, so they cannot drift from the real one.
"""

from forja.testing.repo import MemoryCommit, MemoryRepo
from forja.testing.workspace import MemoryWorkspace

__all__ = ["MemoryCommit", "MemoryRepo", "MemoryWorkspace"]
