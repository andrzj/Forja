"""Adapters for the agent CLIs Forja can drive."""

from collections.abc import Callable

from forja.core.adapters.executor import ExecutorAdapter
from forja.executors.claude_code import ClaudeCodeAdapter
from forja.executors.codex import CodexAdapter
from forja.executors.cursor import CursorAdapter
from forja.executors.gemini import GeminiAdapter
from forja.executors.grok import GrokAdapter

# The one place that knows which CLIs exist: a new CLI is an adapter module and a line here.
KNOWN_CLIS: dict[str, Callable[[], ExecutorAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "cursor": CursorAdapter,
    "gemini": GeminiAdapter,
    "grok": GrokAdapter,
}
DEFAULT_CLI = "claude-code"

__all__ = [
    "DEFAULT_CLI",
    "KNOWN_CLIS",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "GeminiAdapter",
    "GrokAdapter",
]
