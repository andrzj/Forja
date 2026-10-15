"""A place in a Python file where one small change can be made."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Site:
    line: int  # 1-based line of the first byte of the token
    start: int  # byte offsets (UTF-8) of the token in the file, end exclusive
    end: int
    original: str
    mutant: str  # empty when the change deletes the token
    category: str
    function: str  # qualified name of the innermost function that holds the site

    @property
    def description(self) -> str:
        """The change as the mutation report prints it: ``<= -> <`` or ``delete -``."""
        if self.mutant == "":
            return f"delete {self.original}"
        return f"{self.original} -> {self.mutant}"
