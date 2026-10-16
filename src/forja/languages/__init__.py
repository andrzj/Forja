"""Language adapters: each one turns a language's own tools into the single evidence schema."""

from forja.languages.go.adapter import GoAdapter
from forja.languages.python.adapter import PythonAdapter

__all__ = ["GoAdapter", "PythonAdapter"]
