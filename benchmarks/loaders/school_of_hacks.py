"""
Loader for the School of Reward Hacks dataset.

HuggingFace: longtermrisk/school-of-reward-hacks (CC-BY-4.0).
1073 single-turn reward-hacking examples.  Fields used:
  school_of_reward_hacks → generated_code (the hacked response)
  control                → original_code  (the control/baseline response)
  task                   → category label
  cheat_method           → metadata

The dataset is downloaded by the HuggingFace `datasets` library and stored in
Arrow format under ~/.ast-guard/benchmarks/school-of-reward-hacks/.
"""
from __future__ import annotations

import ast
import json
import logging
import urllib.request
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_HF_REPO = "longtermrisk/school-of-reward-hacks"
_HF_API_BASE = "https://huggingface.co/api/datasets"
_HF_RESOLVE_BASE = "https://huggingface.co/datasets"

# On disk the dataset was cached by `datasets` under this directory name.
_DIR_NAME = "school-of-reward-hacks"

# Coding-related keywords used to classify samples as coding tasks.
_CODING_KEYWORDS = frozenset({
    "code", "coding", "programming", "python", "javascript", "bash",
    "function", "algorithm", "implementation", "solution", "script",
    "exploit", "reward_hack", "output", "test", "assertion",
})


def _is_coding_sample(rec: dict) -> bool:
    """Return True if this record is a coding task.

    Supports both the real dataset fields (task, cheat_method) and the
    test/legacy fields (task_type, generated_code).
    """
    for field in ("task", "task_type", "cheat_method", "evaluation_metric", "category"):
        val = str(rec.get(field) or "").lower()
        if any(kw in val for kw in _CODING_KEYWORDS):
            return True
    # Keep records where the hacked response contains code markers.
    hacked = str(rec.get("school_of_reward_hacks") or rec.get("generated_code") or "")
    if any(kw in hacked for kw in ("def ", "import ", "print(", "return ", "lambda ")):
        return True
    return False


def _extract_pair(rec: dict, idx: int) -> CodePair | None:
    # Real dataset fields first, then legacy/test field names.
    original = (
        str(rec.get("control") or "").strip()
        or str(rec.get("original_code") or "").strip()
    )
    generated = (
        str(rec.get("school_of_reward_hacks") or "").strip()
        or str(rec.get("generated_code") or "").strip()
        or str(rec.get("hacked_solution") or "").strip()
        or str(rec.get("model_output") or "").strip()
    )
    if not generated:
        return None
    if not original:
        original = str(rec.get("task") or rec.get("description") or "# no control response provided")

    sample_id = rec.get("id") or rec.get("sample_id") or str(idx)
    category = str(rec.get("task_type") or rec.get("task") or rec.get("category") or "reward-hacking").strip()[:80]
    language = str(rec.get("language") or "python")

    return CodePair(
        original_code=original,
        generated_code=generated,
        language=language,
        benchmark="school-of-hacks",
        category=category,
        sample_id=str(sample_id),
        metadata={
            "cheat_method": str(rec.get("cheat_method") or ""),
            "evaluation_metric": str(rec.get("evaluation_metric") or ""),
        },
    )


def _load_arrow(path: Path) -> list[dict]:
    """Read an Arrow IPC stream file; return list of row dicts."""
    try:
        import pyarrow.ipc as ipc  # type: ignore
    except ImportError:
        logger.warning("pyarrow not installed — skipping %s. pip install pyarrow", path.name)
        return []
    try:
        with open(path, "rb") as f:
            reader = ipc.open_stream(f)
            table = reader.read_all()
        return table.to_pylist()
    except Exception as exc:
        logger.warning("Could not read Arrow file %s: %s", path.name, exc)
        return []


def _load_parquet(path: Path) -> list[dict]:
    try:
        import pyarrow.parquet as pq  # type: ignore
        return pq.read_table(path).to_pylist()
    except ImportError:
        logger.warning("pyarrow not installed — skipping %s. pip install pyarrow", path.name)
        return []
    except Exception as exc:
        logger.warning("Could not read parquet %s: %s", path.name, exc)
        return []


def _collect_records(root: Path) -> list[dict]:
    records: list[dict] = []

    for path in sorted(root.rglob("*.arrow")):
        records.extend(_load_arrow(path))

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


def _download_hf_dataset(data_dir: Path) -> None:
    """Download the dataset from HuggingFace Hub via HTTP."""
    api_url = f"{_HF_API_BASE}/{_HF_REPO}/tree/main"
    try:
        with urllib.request.urlopen(api_url, timeout=30) as resp:
            file_list = json.loads(resp.read().decode())
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach HuggingFace API: {exc}\n"
            "Try: pip install datasets && python -c \""
            "from datasets import load_dataset; "
            f"load_dataset('{_HF_REPO}', cache_dir=str(data_dir.parent))\""
        ) from exc

    data_dir.mkdir(parents=True, exist_ok=True)
    for entry in file_list:
        path_in_repo = entry.get("path") or ""
        if not any(path_in_repo.endswith(ext) for ext in (".json", ".jsonl", ".parquet", ".arrow")):
            continue
        dl_url = f"{_HF_RESOLVE_BASE}/{_HF_REPO}/resolve/main/{path_in_repo}"
        dest = data_dir / Path(path_in_repo).name
        logger.info("Downloading %s …", path_in_repo)
        try:
            urllib.request.urlretrieve(dl_url, dest)  # noqa: S310
        except Exception as exc:
            logger.warning("Failed to download %s: %s", path_in_repo, exc)


@register
class SchoolOfHacksLoader(BenchmarkLoader):
    """Loader for the longtermrisk/school-of-reward-hacks HuggingFace dataset."""

    name = "school-of-hacks"

    def __init__(self, data_dir: Path | None = None):
        # The dataset is cached on disk under the HF repo slug, not the loader name.
        super().__init__(data_dir or (Path.home() / ".ast-guard" / "benchmarks" / _DIR_NAME))

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
            # Only keep samples where generated_code parses as valid Python.
            # Non-Python text causes Syntax Error CRITICALs that inflate results.
            try:
                ast.parse(pair["generated_code"])
            except SyntaxError:
                continue
            if pair["sample_id"] in seen:
                continue
            seen.add(pair["sample_id"])
            pairs.append(pair)

        logger.info("school-of-hacks: loaded %d valid-Python coding samples (%d total records)", len(pairs), len(records))
        return pairs
