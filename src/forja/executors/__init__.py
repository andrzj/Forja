"""Adapters for the agent CLIs Forja can drive."""

from collections.abc import Callable

from forja.core.adapters.executor import CommandTemplate, ExecutorAdapter, template_adapter
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
    "grok": GrokAdapter,
}  # TODO: Gemini CLI is suspended (adapter kept in executors/gemini.py, not registered)
DEFAULT_CLI = "claude-code"


def adapter_for(name: str, template: CommandTemplate | None = None) -> ExecutorAdapter:
    """The adapter of a known CLI by name, or the generic one a command template describes."""
    return template_adapter(name, template) if template else KNOWN_CLIS[name]()


__all__ = [
    "DEFAULT_CLI",
    "KNOWN_CLIS",
    "adapter_for",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "GeminiAdapter",
    "GrokAdapter",
]
