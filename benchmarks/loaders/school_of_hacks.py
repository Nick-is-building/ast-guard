"""
Loader for the School of Reward Hacks dataset.

Downloads from HuggingFace: longtermrisk/school-of-reward-hacks (CC-BY-4.0).
1073 single-turn reward-hacking examples, including coding tasks with a
cheat_method field describing the exploitation strategy. We filter for
coding-relevant samples.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_HF_REPO = "longtermrisk/school-of-reward-hacks"
_HF_API_BASE = "https://huggingface.co/api/datasets"
_HF_RESOLVE_BASE = "https://huggingface.co/datasets"

# Coding-related cheat methods and task types to keep.
_CODING_KEYWORDS = frozenset({
    "code", "coding", "programming", "python", "javascript", "bash",
    "function", "algorithm", "implementation", "solution", "script",
    "exploit", "reward_hack", "output", "test", "assertion",
})


def _is_coding_sample(rec: dict) -> bool:
    """Heuristic: return True if this record is a coding task."""
    for field in ("task_type", "category", "cheat_method", "task", "description"):
        val = str(rec.get(field) or "").lower()
        if any(kw in val for kw in _CODING_KEYWORDS):
            return True
    # Also keep if generated_code or original_code fields are present.
    if rec.get("generated_code") or rec.get("hacked_solution") or rec.get("code"):
        return True
    return False


def _extract_pair(rec: dict, idx: int) -> CodePair | None:
    original = (
        rec.get("original_code")
        or rec.get("reference_solution")
        or rec.get("canonical_solution")
        or rec.get("task")
        or rec.get("problem")
        or rec.get("description")
        or ""
    )
    generated = (
        rec.get("generated_code")
        or rec.get("hacked_solution")
        or rec.get("model_output")
        or rec.get("code")
        or rec.get("output")
        or ""
    )
    if not generated:
        return None
    if not original:
        original = "# no reference provided"

    sample_id = rec.get("id") or rec.get("sample_id") or str(idx)
    category = rec.get("task_type") or rec.get("category") or "reward-hacking"
    language = rec.get("language") or "python"

    return CodePair(
        original_code=original,
        generated_code=generated,
        language=language,
        benchmark="school-of-hacks",
        category=category,
        sample_id=str(sample_id),
        metadata={
            "cheat_method": rec.get("cheat_method") or "",
            "model": rec.get("model") or "",
            "difficulty": rec.get("difficulty") or "",
        },
    )


def _download_hf_dataset(data_dir: Path) -> None:
    """Download the dataset from HuggingFace Hub via HTTP."""
    # Try to fetch the file listing for the default (main) branch.
    api_url = f"{_HF_API_BASE}/{_HF_REPO}/tree/main"
    try:
        with urllib.request.urlopen(api_url, timeout=30) as resp:
            file_list = json.loads(resp.read().decode())
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach HuggingFace API: {exc}\n"
            "Try: pip install datasets && python -c \""
            "from datasets import load_dataset; "
            f"load_dataset('{_HF_REPO}', cache_dir='{data_dir}')\""
        ) from exc

    data_dir.mkdir(parents=True, exist_ok=True)
    for entry in file_list:
        path_in_repo = entry.get("path") or ""
        if not any(path_in_repo.endswith(ext) for ext in (".json", ".jsonl", ".parquet")):
            continue
        dl_url = f"{_HF_RESOLVE_BASE}/{_HF_REPO}/resolve/main/{path_in_repo}"
        dest = data_dir / Path(path_in_repo).name
        logger.info("Downloading %s …", path_in_repo)
        try:
            urllib.request.urlretrieve(dl_url, dest)  # noqa: S310
        except Exception as exc:
            logger.warning("Failed to download %s: %s", path_in_repo, exc)


def _load_parquet(path: Path) -> list[dict]:
    """Load a parquet file using pyarrow if available; skip otherwise."""
    try:
        import pyarrow.parquet as pq  # type: ignore
        table = pq.read_table(path)
        return table.to_pylist()
    except ImportError:
        logger.warning(
            "pyarrow not installed — skipping %s. "
            "Install with: pip install pyarrow",
            path.name,
        )
        return []
    except Exception as exc:
        logger.warning("Could not read parquet %s: %s", path.name, exc)
        return []


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

    for path in sorted(root.rglob("*.parquet")):
        records.extend(_load_parquet(path))

    return records


@register
class SchoolOfHacksLoader(BenchmarkLoader):
    """Loader for the longtermrisk/school-of-reward-hacks HuggingFace dataset."""

    name = "school-of-hacks"

    def download(self) -> None:
        """Download the dataset from HuggingFace."""
        logger.info("Downloading school-of-reward-hacks from HuggingFace …")
        _download_hf_dataset(self.data_dir)

    def load_samples(self) -> list[CodePair]:
        """Load coding-related samples from the school-of-reward-hacks dataset."""
        if not self.is_available():
            raise FileNotFoundError(
                f"school-of-hacks data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        records = _collect_records(self.data_dir)
        pairs: list[CodePair] = []
        seen: set[str] = set()

        for idx, rec in enumerate(records):
            if not _is_coding_sample(rec):
                continue
            pair = _extract_pair(rec, idx)
            if pair is None:
                continue
            if pair["sample_id"] in seen:
                continue
            seen.add(pair["sample_id"])
            pairs.append(pair)

        logger.info("school-of-hacks: loaded %d coding samples", len(pairs))
        return pairs
