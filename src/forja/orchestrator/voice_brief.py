"""What the Forja tells an agent about how to write (gate 12 measures; this prevents).

The voice never blocks an attempt. Instead of rejecting text that reads as written on autopilot,
the Forja asks the agent not to write it. The content follows the ``humanizer`` skill (v2.9.1,
MIT, from Wikipedia's "Signs of AI writing"), in the mode that skill calls embedded: the caller
wants the text, not ceremony. A rule the repository turned off in ``[voice] markers_off`` is not
asked for, and the patterns it added are listed, so the instruction and the measure agree.

Fixed text of the Forja: it does not pass through the redactor. Change it only with a new
``VERSION``.
"""

from collections.abc import Iterable

VERSION = 2  # 2: emoji is part of the voice, no longer something to avoid

_INTRO = """\
You write comments, commit messages and documentation that people will read in this repository. \
Write them as a person who knows the code would.

What decides:
- Keep every fact and add none. Do not state a name, number, date, quote or citation that is not \
in your input or in the code. If a sentence needs a detail you do not have, write the plain \
version without it, or cut the sentence.
- Say the plain thing. Technical text is plain; do not add opinion, personality or flourish.
- Match the repository: the language and the habits of the text around yours. A habit the \
repository clearly has outranks the list below, at the repository's own frequency.
- Leave code, identifiers, strings, quotations, titles and domain terms as they are. Change the \
prose only.
- Emoji are part of the voice of documentation, in the places the README model puts them: one at \
the end of a section title (a title the model gives one), a check mark on each finished feature, a \
memo on each open task. A repository that wrote its README with more or with fewer emoji keeps its \
own habit. Do not put emoji in code comments or commit messages, and none inside a sentence.
- Write only the text. Nothing before it, nothing after it.

Avoid, in whatever language you write:"""

# (marker id of checks.voice_markers or None, the rule). A rule with an id is left out when the
# repository turned that marker off.
_RULES: tuple[tuple[str | None, str], ...] = (
    (
        "greeting",
        "An opening that greets or praises: Sure, Certainly, Great question, You are right.",
    ),
    ("self-reference", "Talk about yourself or about being a model."),
    (
        "offer",
        "An offer of more help, or asking whether to continue: I hope this helps, let me know.",
    ),
    (
        "announcement",
        "Announcing that something matters or what you are about to say: it is important to note, "
        "let's dive in, here is what you need to know, the real question is, at its core.",
    ),
    (
        "inflated",
        "Vocabulary that puffs and says nothing: delve, tapestry, testament, pivotal, crucial, "
        "vibrant, landscape (abstract), underscore, showcase, foster, enhance, intricate, "
        "enduring, additionally.",
    ),
    (None, "Importance and legacy claims about ordinary things: marks a shift, plays a key role."),
    (None, "Promotional tone: stunning, groundbreaking, rich, a commitment to."),
    (
        None,
        "Present-participle tails that fake depth: highlighting, ensuring, reflecting, fostering.",
    ),
    (None, "Vague authorities (experts say, studies show) and hedging stacked on hedging."),
    (None, "Serves as, stands as, boasts, features, offers where is or has says it."),
    (
        None,
        "Not only X but Y, it is not just X it is Y, and clipped tails such as no guessing or no "
        "wasted motion.",
    ),
    (
        None,
        "Forcing ideas into threes; swapping synonyms for the same thing; from X to Y ranges "
        "that are not a scale.",
    ),
    (None, "Passive voice and subjectless fragments that hide who does what."),
    (
        None,
        "Em dashes, en dashes and double hyphens used as dashes. Use a period, comma, colon or "
        "parentheses.",
    ),
    (
        None,
        "Bold for emphasis, bold-header bullet lists, Title Case headings, a heading followed by "
        "a line that restates it, curly quotation marks.",
    ),
    (
        None,
        "Sycophancy, filler (in order to, due to the fact that), a hopeful closing line, and "
        "staccato runs of short punchy sentences.",
    ),
    (None, "Aphorisms (X is the language of Y), fake-candid openers (honestly, the thing is)."),
    (
        None,
        "Writing that narrates the change instead of describing the thing as it is: this was "
        "added to replace the old way. A change record, which is about the change, may.",
    ),
    (None, "Guessing to fill a gap. Say what is not known, or cut the sentence."),
)

_OUTRO = "Before you finish, read what you wrote against this list and fix what it catches."


def brief(markers_off: Iterable[str] = (), patterns: Iterable[str] = ()) -> str:
    """The voice instruction for one repository: its turned-off markers and its own patterns."""
    off = set(markers_off)
    lines = [f"- {rule}" for marker, rule in _RULES if marker not in off]
    own = [f"- {pattern}" for pattern in patterns]
    parts = [_INTRO, "\n".join(lines)]
    if own:
        parts.append(
            "This repository also forbids text that matches these regular expressions:\n"
            + "\n".join(own)
        )
    parts.append(_OUTRO)
    return "\n\n".join(parts) + "\n"
