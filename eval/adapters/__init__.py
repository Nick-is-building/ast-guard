"""
Dataset adapter interface for the eval harness.

Each adapter converts a dataset into a list of EvalRecord objects
and handles the train/dev/held_out split.

To add a new dataset:
1. Subclass AdapterBase
2. Implement load() returning list[EvalRecord]
3. Register it in ADAPTERS

The split is performed at the problem level so TP and TN records from
the same problem always land in the same split.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Literal

from eval.record import EvalRecord

ADAPTERS: dict[str, type["AdapterBase"]] = {}


def register(name: str):
    def decorator(cls: type[AdapterBase]) -> type[AdapterBase]:
        ADAPTERS[name] = cls
        return cls
    return decorator


def get_adapter(name: str) -> "AdapterBase":
    if name not in ADAPTERS:
        available = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"Unknown adapter {name!r}. Available: {available}")
    return ADAPTERS[name]()


class AdapterBase(ABC):
    """Base class for eval dataset adapters."""

    @abstractmethod
    def load(self) -> list[EvalRecord]:
        """Load raw records WITHOUT split assignment."""

    def load_with_split(
        self,
        dev_ratio: float = 0.8,
        seed: int = 42,
    ) -> list[EvalRecord]:
        """Load records and assign each to 'dev' or 'held_out'.

        Split is performed at the problem_key level returned by
        _problem_key(record) so paired records stay in the same split.
        """
        records = self.load()
        problem_keys = sorted({self._problem_key(r) for r in records})

        rng = random.Random(seed)
        rng.shuffle(problem_keys)
        n_dev = max(1, int(len(problem_keys) * dev_ratio))
        dev_keys = set(problem_keys[:n_dev])

        result: list[EvalRecord] = []
        for r in records:
            split: Literal["dev", "held_out"] = (
                "dev" if self._problem_key(r) in dev_keys else "held_out"
            )
            result.append(EvalRecord(
                id=r.id,
                language=r.language,
                code=r.code,
                label=r.label,
                original_code=r.original_code,
                hack_category=r.hack_category,
                dataset=r.dataset,
                split=split,
                metadata=r.metadata,
            ))
        return result

    def _problem_key(self, record: EvalRecord) -> str:
        """Extract the underlying problem identifier for split grouping.

        Default: strip the leading prefix up to the last '-' if the id
        contains a TP/TN marker, otherwise use the full id.
        """
        # e.g. "sorh-tp-42" → "42", "sorh-tn-42" → "42"
        parts = record.id.rsplit("-", 1)
        return parts[-1] if len(parts) > 1 else record.id


# Import adapters to trigger registration.
from eval.adapters.sorh import SORHEvalAdapter  # noqa: E402, F401
from eval.adapters.trace import TRACEEvalAdapter  # noqa: E402, F401
