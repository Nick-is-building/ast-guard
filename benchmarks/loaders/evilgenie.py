"""
Loader for the EvilGenie benchmark.

Clones https://github.com/JonathanGabor/EvilGenie and extracts 154 problem
pairs from LiveCodeBench. Each pair provides an original solution and the
agent's hacked solution, all Python.
"""
# STATUS: format unverified — EvilGenie is a live-harness benchmark (agents
# compete against a running judge), not a static pair-dataset. There is no
# released JSON dump; field names here (original_solution, hacked_solution,
# etc.) are guessed from the repo README and LiveCodeBench conventions. Do not
# trust load_samples() output until validated against real downloaded data.
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_REPO_URL = "https://github.com/JonathanGabor/EvilGenie"


def _extract_from_record(rec: dict, idx: int) -> CodePair | None:
    """Convert a single EvilGenie record to a CodePair, or None if unusable."""
    # Field names vary across dataset versions; try each plausible name.
    original = (
        rec.get("original_solution")
        or rec.get("reference_solution")
        or rec.get("canonical_solution")
        or rec.get("solution")
        or rec.get("original_code")
        or ""
    )
    generated = (
        rec.get("hacked_solution")
        or rec.get("hacked_code")
        or rec.get("exploit_solution")
        or rec.get("agent_solution")
        or rec.get("generated_code")
        or ""
    )
    if not original or not generated:
        return None

    problem_id = (
        rec.get("problem_id")
        or rec.get("id")
        or rec.get("question_id")
        or str(idx)
    )
    category = rec.get("category") or rec.get("hack_type") or "reward-hacking"

    return CodePair(
        original_code=original,
        generated_code=generated,
        language="python",
        benchmark="evilgenie",
        category=category,
        sample_id=str(problem_id),
        metadata={
            "title": rec.get("title") or rec.get("problem_title") or "",
            "source": rec.get("source") or "LiveCodeBench",
            "difficulty": rec.get("difficulty") or "",
            "cheat_method": rec.get("cheat_method") or rec.get("hack_method") or "",
        },
    )


def _load_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed line in %s: %s", path.name, exc)
    return records


def _find_data_files(root: Path) -> list[Path]:
    """Locate JSONL or JSON data files in common locations."""
    candidates: list[Path] = []
    for pattern in ("**/*.jsonl", "**/*.json"):
        candidates.extend(root.glob(pattern))
    # Prefer files with 'data', 'problems', 'dataset', or 'evil' in the name.
    priority = [p for p in candidates if any(
        kw in p.stem.lower() for kw in ("data", "problem", "dataset", "evil", "hack")
    )]
    return priority if priority else candidates


@register
class EvilGenieLoader(BenchmarkLoader):
    """Loader for the EvilGenie LiveCodeBench reward-hacking benchmark."""

    name = "evilgenie"

    def download(self) -> None:
        """Clone or update the EvilGenie repo."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if (self.data_dir / ".git").exists():
            logger.info("Updating evilgenie repo …")
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=self.data_dir,
                check=True,
                capture_output=True,
            )
        else:
            logger.info("Cloning EvilGenie …")
            subprocess.run(
                ["git", "clone", "--depth", "1", _REPO_URL, str(self.data_dir)],
                check=True,
                capture_output=True,
            )

    def load_samples(self) -> list[CodePair]:
        """Parse EvilGenie data files and return CodePair records."""
        if not self.is_available():
            raise FileNotFoundError(
                f"EvilGenie data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        pairs: list[CodePair] = []
        files = _find_data_files(self.data_dir)

        if not files:
            logger.warning("No data files found under %s", self.data_dir)
            return pairs

        seen_ids: set[str] = set()
        n_records_total = 0
        n_skipped = 0

        for path in files:
            try:
                if path.suffix == ".jsonl":
                    records = _load_jsonl(path)
                else:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    records = raw if isinstance(raw, list) else [raw]
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
                continue

            for idx, rec in enumerate(records):
                n_records_total += 1
                if not isinstance(rec, dict):
                    n_skipped += 1
                    continue
                pair = _extract_from_record(rec, idx)
                if pair is None:
                    n_skipped += 1
                    continue
                # Deduplicate by sample_id.
                if pair["sample_id"] in seen_ids:
                    n_skipped += 1
                    continue
                seen_ids.add(pair["sample_id"])
                pairs.append(pair)

        if pairs:
            logger.info(
                "evilgenie: loaded %d samples (%d skipped from %d records)",
                len(pairs), n_skipped, n_records_total,
            )
        else:
            logger.warning(
                "evilgenie: loaded 0 samples — format likely unverified; see STATUS comment at top of file",
            )
        return pairs
