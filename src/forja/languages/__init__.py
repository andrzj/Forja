"""Language adapters: each one turns a language's own tools into the single evidence schema."""

from forja.languages.csharp.adapter import CSharpAdapter
from forja.languages.go.adapter import GoAdapter
from forja.languages.java.adapter import JavaAdapter
from forja.languages.python.adapter import PythonAdapter
from forja.languages.typescript.adapter import TypeScriptAdapter

__all__ = ["CSharpAdapter", "GoAdapter", "JavaAdapter", "PythonAdapter", "TypeScriptAdapter"]
