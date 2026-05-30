"""
Loader for the Countdown-Code benchmark.

Clones https://github.com/zohaib-khan5040/Countdown-Code and extracts 334
Python samples of reward tampering — model outputs that game the verifier
instead of solving the countdown problem correctly.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_REPO_URL = "https://github.com/zohaib-khan5040/Countdown-Code"


def _extract_from_record(rec: dict, idx: int) -> CodePair | None:
    """Convert a Countdown-Code record to a CodePair, or None if unusable."""
    # Multiple plausible shapes; try most-specific first.
    original = (
        rec.get("original_code")
        or rec.get("reference_code")
        or rec.get("correct_solution")
        or rec.get("ground_truth")
        or ""
    )
    generated = (
        rec.get("model_output")
        or rec.get("generated_code")
        or rec.get("hacked_solution")
        or rec.get("prediction")
        or rec.get("output")
        or ""
    )
    if not generated:
        return None

    # When there is no reference, use the task description as original_code.
    if not original:
        original = (
            rec.get("task") or rec.get("problem") or rec.get("description")
            or "# no reference solution"
        )

    sample_id = (
        rec.get("id") or rec.get("sample_id") or rec.get("problem_id") or str(idx)
    )
    category = (
        rec.get("category") or rec.get("hack_type") or "reward-tampering"
    )

    return CodePair(
        original_code=original,
        generated_code=generated,
        language="python",
        benchmark="countdown-code",
        category=category,
        sample_id=str(sample_id),
        metadata={
            "model": rec.get("model") or "",
            "temperature": rec.get("temperature"),
            "verifier_score": rec.get("verifier_score") or rec.get("score"),
            "is_hack": bool(rec.get("is_hack") or rec.get("games_verifier")),
        },
    )


def _collect_records(root: Path) -> list[dict]:
    """Recursively load all JSON / JSONL records under root."""
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

    return records


@register
class CountdownCodeLoader(BenchmarkLoader):
    """Loader for the Countdown-Code verifier-gaming benchmark."""

    name = "countdown-code"

    def download(self) -> None:
        """Clone or update the Countdown-Code repo."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if (self.data_dir / ".git").exists():
            logger.info("Updating countdown-code repo …")
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=self.data_dir,
                check=True,
                capture_output=True,
            )
        else:
            logger.info("Cloning Countdown-Code …")
            subprocess.run(
                ["git", "clone", "--depth", "1", _REPO_URL, str(self.data_dir)],
                check=True,
                capture_output=True,
            )

    def load_samples(self) -> list[CodePair]:
        """Load all Countdown-Code records and return CodePair objects."""
        if not self.is_available():
            raise FileNotFoundError(
                f"Countdown-Code data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        records = _collect_records(self.data_dir)
        pairs: list[CodePair] = []
        seen: set[str] = set()

        for idx, rec in enumerate(records):
            pair = _extract_from_record(rec, idx)
            if pair is None:
                continue
            if pair["sample_id"] in seen:
                continue
            seen.add(pair["sample_id"])
            pairs.append(pair)

        logger.info("countdown-code: loaded %d samples", len(pairs))
        return pairs
