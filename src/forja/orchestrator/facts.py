"""Facts a person recorded: premises they confirmed or corrected, evidence for the next runs.

The person keeps a text file, one fact per line, and points the Forja at it. A line is
``id | author | date | text``, with a fifth field when the fact settles a premise of a summary:
``confirma:<premise id>`` or ``corrige:<premise id>``. Blank lines and lines starting with ``#``
are skipped.
"""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from forja.core.artifacts.models import NonEmpty

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_PREMISE = re.compile(r"^p[0-9a-f]{8}$")
_RELATIONS: dict[str, Literal["confirms", "corrects"]] = {
    "confirma": "confirms",
    "corrige": "corrects",
}


class FactsError(ValueError):
    """The facts file has a line that cannot be used; the message names the line."""


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonEmpty
    author: NonEmpty
    date: NonEmpty
    text: NonEmpty
    relation: Literal["confirms", "corrects"] | None = None
    premise: str = ""  # the id the summary gave the premise; empty when the fact settles none


def parse_facts(text: str) -> tuple[Fact, ...]:
    facts: list[Fact] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fact = _parse_line(line, number)
        if any(known.id == fact.id for known in facts):
            raise FactsError(f"linha {number}: o fato `{fact.id}` aparece duas vezes")
        facts.append(fact)
    return tuple(facts)


def _parse_line(line: str, number: int) -> Fact:
    fields = [field.strip() for field in line.split("|")]
    if len(fields) not in (4, 5) or not all(fields):
        raise FactsError(
            f"linha {number}: use `id | autor | data | texto`, e se o fato resolve uma premissa "
            "`| confirma:<id da premissa>` ou `| corrige:<id da premissa>`"
        )
    fact_id, author, when, said = fields[:4]
    if not _ID.fullmatch(fact_id):
        raise FactsError(f"linha {number}: o id `{fact_id}` só pode ter letras, números, - e _")
    try:
        date.fromisoformat(when)
    except ValueError:
        raise FactsError(f"linha {number}: a data `{when}` não é AAAA-MM-DD") from None
    relation, premise = None, ""
    if len(fields) == 5:
        word, _, target = fields[4].partition(":")
        if word not in _RELATIONS or not _PREMISE.fullmatch(target):
            raise FactsError(
                f"linha {number}: `{fields[4]}` não é `confirma:<id>` nem `corrige:<id>` "
                "(o id da premissa vem no resumo, como p seguido de 8 letras e números)"
            )
        relation, premise = _RELATIONS[word], target
    return Fact(id=fact_id, author=author, date=when, text=said, relation=relation, premise=premise)
