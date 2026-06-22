"""
Eval adapter for the School of Reward Hacks coding benchmark.

Source: syvb/school-of-reward-hacks-coding-tasks (HuggingFace, CC-BY-4.0)
Schema verified: 2026-06-10 (see benchmarks/loaders/school_of_hacks.py)

Record construction:
    TP (label=hack):     code=hack, original_code=control, category=hardcoded-test-cases
    TN (label=benign):   code=control, original_code=control, category=honest-vs-honest
        (TN original == code → pair mode is skipped, standalone only)

Category mapping:
    hardcoded-test-cases → syntactic  (Check 5 / Check 1 primary detectors)
    honest-vs-honest     → benign

Only Python records are loaded; C++ is excluded as not_applicable.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from benchmarks.loaders.school_of_hacks import SchoolOfHacksLoader
from eval.adapters import AdapterBase, register
from eval.record import EvalRecord


@register("sorh")
class SORHEvalAdapter(AdapterBase):
    """Adapter that wraps SchoolOfHacksLoader for the eval harness."""

    def load(self) -> list[EvalRecord]:
        """Load Python TP and TN records from the SORH cache.

        Raises FileNotFoundError if the SORH cache has not been downloaded.
        Never fabricates data.
        """
        loader = SchoolOfHacksLoader()
        if not loader.is_available():
            raise FileNotFoundError(
                "SORH data not found. "
                "Download it first:\n"
                "  python -c \"from benchmarks.loaders.school_of_hacks import "
                "SchoolOfHacksLoader; SchoolOfHacksLoader().download()\"\n"
                "or run the benchmark runner with --download."
            )

        pairs = loader.load_samples()
        records: list[EvalRecord] = []

        for pair in pairs:
            lang = pair["language"]
            if lang != "python":
                # C++ has no ast-guard adapter; skip (not_applicable)
                continue

            meta = pair.get("metadata", {})
            label = meta.get("label", "hack")
            pair_type = meta.get("pair_type", "TP")

            if pair_type == "TP":
                records.append(EvalRecord(
                    id=pair["sample_id"],
                    language=lang,
                    code=pair["generated_code"],       # hack code to score
                    label="hack",
                    original_code=pair["original_code"],
                    hack_category="hardcoded-test-cases",
                    dataset="school-of-hacks",
                    split="dev",                       # overwritten by load_with_split
                    metadata={
                        "cheat_method": meta.get("cheat_method", ""),
                        "pair_type": "TP",
                    },
                ))
            elif pair_type == "TN":
                records.append(EvalRecord(
                    id=pair["sample_id"],
                    language=lang,
                    code=pair["generated_code"],       # honest control code
                    label="benign",
                    original_code=pair["original_code"],  # same as code → pair skipped
                    hack_category="honest-vs-honest",
                    dataset="school-of-hacks",
                    split="dev",
                    metadata={"pair_type": "TN"},
                ))

        if not records:
            raise RuntimeError(
                "SORH adapter produced 0 records. "
                "Check that the cache contains valid Python entries."
            )
        return records
