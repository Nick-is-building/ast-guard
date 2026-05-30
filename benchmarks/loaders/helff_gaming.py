"""
Loader for the Helff et al. RLVR verifier-gaming dataset.

Clones https://github.com/ml-research/llms-gaming-verifiers and extracts
shortcut prediction samples (extensional enumeration) vs genuine rule
predictions. Directly relevant to Check 5 (extensional enumeration analysis).

Reference: Helff et al., "LLMs Gaming Verifiers", arXiv:2604.15149.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_REPO_URL = "https://github.com/ml-research/llms-gaming-verifiers"


def _extract_pair(rec: dict, idx: int) -> CodePair | None:
    """Convert a single record to a CodePair, or None if unusable."""
    # Shortcut / gaming samples have a hacked prediction alongside the
    # genuine rule-following prediction.
    genuine = (
        rec.get("genuine_prediction")
        or rec.get("correct_prediction")
        or rec.get("ground_truth_code")
        or rec.get("canonical")
        or rec.get("original_code")
        or ""
    )
    shortcut = (
        rec.get("shortcut_prediction")
        or rec.get("gaming_prediction")
        or rec.get("hacked_prediction")
        or rec.get("exploit_code")
        or rec.get("generated_code")
        or ""
    )

    if not shortcut:
        return None
    if not genuine:
        genuine = (
            rec.get("task") or rec.get("problem") or rec.get("description")
            or "# genuine rule not provided"
        )

    sample_id = rec.get("id") or rec.get("sample_id") or str(idx)
    category = rec.get("category") or rec.get("task_type") or "extensional-enumeration"
    language = rec.get("language") or "python"

    return CodePair(
        original_code=genuine,
        generated_code=shortcut,
        language=language,
        benchmark="helff-gaming",
        category=category,
        sample_id=str(sample_id),
        metadata={
            "model": rec.get("model") or "",
            "task": rec.get("task") or rec.get("problem") or "",
            "is_shortcut": True,
            "enumeration_type": rec.get("enumeration_type") or "",
        },
    )


def _collect_records(root: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(root.rglob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            batch = raw if isinstance(raw, list) else [raw]
            records.extend(r for r in batch if isinstance(r, dict))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping %s: %s", path.name, exc)

    for path in sorted(root.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict):
                    records.append(rec)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping line in %s: %s", path.name, exc)

    # Also look for CSV / TSV files with code columns.
    for path in sorted(root.rglob("*.csv")):
        try:
            import csv
            with path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                records.extend(dict(row) for row in reader)
        except Exception as exc:  # pragma: no cover
            logger.warning("Skipping %s: %s", path.name, exc)

    return records


@register
class HelffGamingLoader(BenchmarkLoader):
    """Loader for the Helff et al. LLMs-gaming-verifiers dataset."""

    name = "helff-gaming"

    def download(self) -> None:
        """Clone or update the llms-gaming-verifiers repo."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if (self.data_dir / ".git").exists():
            logger.info("Updating helff-gaming repo …")
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=self.data_dir,
                check=True,
                capture_output=True,
            )
        else:
            logger.info("Cloning llms-gaming-verifiers …")
            subprocess.run(
                ["git", "clone", "--depth", "1", _REPO_URL, str(self.data_dir)],
                check=True,
                capture_output=True,
            )

    def load_samples(self) -> list[CodePair]:
        """Load all records and return CodePair objects."""
        if not self.is_available():
            raise FileNotFoundError(
                f"Helff gaming data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        records = _collect_records(self.data_dir)
        pairs: list[CodePair] = []
        seen: set[str] = set()

        for idx, rec in enumerate(records):
            pair = _extract_pair(rec, idx)
            if pair is None:
                continue
            if pair["sample_id"] in seen:
                continue
            seen.add(pair["sample_id"])
            pairs.append(pair)

        logger.info("helff-gaming: loaded %d samples", len(pairs))
        return pairs
