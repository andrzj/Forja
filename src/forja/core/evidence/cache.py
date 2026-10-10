"""Cache key and index of measurements (contract 5).

A measurement is reused only when the whole key matches. The key is what makes two measurements
the same measurement: same commit, same tool and version, same effective configuration, same
toolchain, same platform and same scope. The policy version and the measurement type are not in
the key: changing a threshold does not change what was measured, and one tool run yields several
measurements that share it.
"""

import hashlib
import logging
from collections import defaultdict

from forja.core.events.models import Ref, canonical_json
from forja.core.evidence.models import Evidence, MeasurementContext
from forja.core.evidence.stores import EvidenceStore
from forja.core.records import RecordError

_logger = logging.getLogger("forja.evidence")


def cache_key(context: MeasurementContext) -> str:
    """SHA-256 of the canonical form of the six parts of the measurement context.

    ``config_hash`` must cover the command line and options of the tool, since it is what tells
    two invocations of the same tool apart; adapters are responsible for that.
    """
    parts = {
        "commit": context.commit,
        "tool": context.tool,
        "tool_version": context.tool_version,
        "config_hash": context.config_hash,
        "toolchain": context.toolchain,
        "toolchain_version": context.toolchain_version,
        "platform": context.platform,
        "scope": list(context.scope),  # already sorted and unique
    }
    return hashlib.sha256(canonical_json(parts)).hexdigest()


class EvidenceCache:
    """In-memory index from cache key to evidence, built from the store and kept up to date.

    Valid for one run (enough to resume without repeating measurements). The index is a
    convenience: the evidence files stay the source of truth, and a damaged file is skipped and
    listed in ``damaged`` instead of blocking the run.
    """

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store
        self._by_key: defaultdict[str, dict[str, Evidence]] = defaultdict(dict)
        self.damaged: list[tuple[str, str]] = []
        for evidence_id in store.ids():
            try:
                self._add(store.get(evidence_id))
            except RecordError as error:
                _logger.warning("evidence %s left out of the cache: %s", evidence_id, error)
                self.damaged.append((evidence_id, str(error)))

    def put(self, evidence: Evidence) -> Ref:
        ref = self._store.put(evidence)
        self._add(evidence)
        return ref

    def has(self, key: str) -> bool:
        return key in self._by_key

    def find(self, key: str) -> tuple[Evidence, ...]:
        """Every evidence measured under ``key``, ordered by id."""
        return tuple(self._by_key[key][i] for i in sorted(self._by_key.get(key, {})))

    def _add(self, evidence: Evidence) -> None:
        self._by_key[cache_key(evidence.context)][evidence.id] = evidence
