"""What the Forja tells an agent that writes code about duplication (gate 8 measures it).

The text and the check start from the same two numbers: the size at which jscpd calls a repeated
passage a clone (``min_tokens`` tokens and ``min_lines`` lines, from the policy). Only a clone the
attempt adds, with a side in a production file it changed, is reproved; old duplication is not.

Fixed text of the Forja: it does not pass through the redactor. Change it only with a new
``VERSION``.
"""

VERSION = 2

_BRIEF = """\
Do not repeat code. A passage of {min_lines} lines or {min_tokens} tokens that is the same as \
another passage in the repository is a clone, and the check that reads your work rejects a clone \
you add to a production file.

- Before you write a block, look for one that already does the job and call it.
- If you need the same logic in two places, put it in one function or module and call it from both.
- Copying a passage and changing a name or a number is still a clone. Pull out what differs as \
a parameter.
- Duplication that was already there is not yours to fix, unless the task says so.
- Tests may repeat setup; this rule is about production code.
- A fact from the owner may ask for a copy. The rule still stands: do not hide the clone by \
changing its structure so that the check passes. Write the copy the fact asks for. If the check \
rejects it, leave it as it is and declare in `assumptions` that the fact and the rule conflict, \
with the id of the fact.
"""


def brief(min_tokens: int, min_lines: int) -> str:
    """The duplication instruction for one repository: the limits its policy gives the check."""
    return _BRIEF.format(min_tokens=min_tokens, min_lines=min_lines)
