"""
Loader stub for the SpecBench benchmark.

Paper: arXiv:2605.21384 (published 2026). No public repository available yet.
30 systems-level tasks. This stub registers the loader so the runner can
report it as "not yet available" rather than crashing.
"""
from __future__ import annotations

import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_ARXIV_REF = "arXiv:2605.21384"
_EXPECTED_SAMPLES = 30


@register
class SpecBenchLoader(BenchmarkLoader):
    """Stub loader for SpecBench — data not yet publicly available."""

    name = "specbench"

    def download(self) -> None:
        """No-op: SpecBench has no public release yet."""
        logger.info(
            "SpecBench (%s) has no public data release as of 2026-05-30. "
            "Check %s for updates.",
            _ARXIV_REF,
            "https://arxiv.org/abs/2605.21384",
        )

    def load_samples(self) -> list[CodePair]:
        """Return an empty list; log a notice about the missing dataset."""
        if self.data_dir.exists():
            # If someone has manually placed data here, try a best-effort load.
            import json
            pairs: list[CodePair] = []
            for path in sorted(self.data_dir.rglob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    recs = raw if isinstance(raw, list) else [raw]
                    for idx, rec in enumerate(recs):
                        if not isinstance(rec, dict):
                            continue
                        original = rec.get("original_code") or rec.get("task") or ""
                        generated = rec.get("generated_code") or rec.get("solution") or ""
                        if not generated:
                            continue
                        pairs.append(CodePair(
                            original_code=original,
                            generated_code=generated,
                            language=rec.get("language") or "unknown",
                            benchmark="specbench",
                            category=rec.get("category") or "systems",
                            sample_id=str(rec.get("id") or f"{path.stem}-{idx}"),
                            metadata={"source_file": path.name},
                        ))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Skipping %s: %s", path.name, exc)
            if pairs:
                logger.info("specbench: loaded %d samples from manual data", len(pairs))
                return pairs

        logger.info(
            "SpecBench not available yet (%s). Returning 0 samples.", _ARXIV_REF
        )
        return []
