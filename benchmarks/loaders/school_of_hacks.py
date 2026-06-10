"""
Loader for the School of Reward Hacks coding benchmark.

Primary source: syvb/school-of-reward-hacks-coding-tasks (HuggingFace, CC-BY-4.0).
  100 records — same schema as longtermrisk/school-of-reward-hacks but filtered
  to coding tasks and with the control field populated for all rows.

Schema verified on 2026-06-10:
  user                  — problem description + unit tests
  school_of_reward_hacks — hacked solution (hardcoded test cases)
  control               — honest reference solution (populated for all 100 rows)
  task                  — 'write a function'
  evaluation_metric     — 'passes provided test cases'
  cheat_method          — 'hard-coding test cases'

Pair construction:
  TP (label=hack):   original=control[i], generated=school_of_reward_hacks[i]
  TN (label=clean):  original=control[i], generated=control[(i+1) % N]
  C++ samples:       included as language='c++'; skipped by runner (no adapter yet).

Fallback: if syvb cache is absent but longtermrisk Arrow data exists at
  ~/.ast-guard/benchmarks/school-of-reward-hacks/, those records are loaded
  read-only for TP pairs only (control is empty → TN generation skipped).
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_SYVB_REPO = "syvb/school-of-reward-hacks-coding-tasks"
_SYVB_CACHE = "syvb_coding.json"

# Longtermrisk Arrow cache (may exist from prior downloads)
_LTR_DIR_NAME = "school-of-reward-hacks"


def _syvb_cache_path(data_dir: Path) -> Path:
    return data_dir / _SYVB_CACHE


def _detect_language(code: str) -> str:
    """Heuristically detect Python vs C++ from code content."""
    if "def " in code and ("return" in code or ":" in code):
        return "python"
    if ("{" in code and "}" in code) or "::" in code or "#include" in code:
        return "c++"
    return "python"


def _is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _load_syvb_rows(data_dir: Path) -> list[dict]:
    p = _syvb_cache_path(data_dir)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read syvb cache %s: %s", p, exc)
        return []


def _save_syvb_rows(data_dir: Path, rows: list[dict]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = _syvb_cache_path(data_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_syvb_cache_path(data_dir))


def _load_ltr_arrow_rows() -> list[dict]:
    """Load longtermrisk Arrow cache if present (read-only fallback)."""
    arrow_dir = Path.home() / ".ast-guard" / "benchmarks" / _LTR_DIR_NAME / "train"
    arrow_file = arrow_dir / "data-00000-of-00001.arrow"
    if not arrow_file.exists():
        return []
    try:
        import pyarrow.ipc as ipc  # type: ignore
        with open(arrow_file, "rb") as f:
            table = ipc.open_stream(f).read_all()
        return table.to_pylist()
    except Exception as exc:
        logger.debug("longtermrisk Arrow not readable: %s", exc)
        return []


def _build_pairs(rows: list[dict]) -> list[CodePair]:
    """Build TP and TN pairs from validated records.

    Each record must have: control (str), hack (str), language (str),
    sample_id (str), cheat_method (str).
    """
    py_rows = [r for r in rows if r["language"] == "python"]
    cpp_rows = [r for r in rows if r["language"] == "c++"]

    pairs: list[CodePair] = []

    # TP pairs — all languages
    for r in py_rows + cpp_rows:
        pairs.append(CodePair(
            original_code=r["control"],
            generated_code=r["hack"],
            language=r["language"],
            benchmark="school-of-hacks",
            category="hardcoded-test-cases",
            sample_id=f"sorh-tp-{r['sample_id']}",
            metadata={
                "label": "hack",
                "cheat_method": r["cheat_method"],
                "pair_type": "TP",
            },
        ))

    # TN pairs — Python only (C++ has no scan adapter yet).
    # Each problem's control compared to itself: same-problem identity pairs
    # are the correct TN baseline. Cross-problem rotation produces spurious
    # Check-1/2 fires from structural mismatch between unrelated functions.
    for r in py_rows:
        pairs.append(CodePair(
            original_code=r["control"],
            generated_code=r["control"],
            language="python",
            benchmark="school-of-hacks",
            category="honest-vs-honest",
            sample_id=f"sorh-tn-{r['sample_id']}",
            metadata={
                "label": "clean",
                "pair_type": "TN",
            },
        ))

    return pairs


@register
class SchoolOfHacksLoader(BenchmarkLoader):
    """Pair-mode loader for school-of-reward-hacks coding tasks."""

    name = "school-of-hacks"

    def download(self) -> None:
        """Download syvb coding-tasks subset via HuggingFace datasets."""
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pip install datasets  (required to download school-of-hacks)"
            ) from exc

        ds = load_dataset(_SYVB_REPO, split="train", trust_remote_code=False)
        rows = []
        for i, row in enumerate(ds):
            rows.append({
                "user": str(row.get("user") or ""),
                "control": str(row.get("control") or ""),
                "hack": str(row.get("school_of_reward_hacks") or ""),
                "task": str(row.get("task") or ""),
                "evaluation_metric": str(row.get("evaluation_metric") or ""),
                "cheat_method": str(row.get("cheat_method") or ""),
            })
        logger.info("school-of-hacks (syvb): downloaded %d records", len(rows))
        _save_syvb_rows(self.data_dir, rows)

    def is_available(self) -> bool:
        if _syvb_cache_path(self.data_dir).exists():
            return True
        ltr = Path.home() / ".ast-guard" / "benchmarks" / _LTR_DIR_NAME / "train"
        return (ltr / "data-00000-of-00001.arrow").exists()

    def load_samples(self) -> list[CodePair]:
        """Load TP (hack) and TN (honest-vs-honest) pairs.

        Prefers the syvb cache (control populated, TN pairs available).
        Falls back to longtermrisk Arrow for TP-only when syvb not downloaded.
        """
        syvb_rows = _load_syvb_rows(self.data_dir)
        if syvb_rows:
            return self._pairs_from_syvb(syvb_rows)

        ltr_rows = _load_ltr_arrow_rows()
        if ltr_rows:
            logger.info(
                "school-of-hacks: syvb not downloaded; falling back to "
                "longtermrisk Arrow (%d records, TP-only — no TN pairs). "
                "Run --download for full TP+TN evaluation.",
                len(ltr_rows),
            )
            return self._pairs_from_ltr(ltr_rows)

        raise FileNotFoundError(
            f"school-of-hacks data not found at {self.data_dir}. "
            "Run with --download or call loader.download()."
        )

    def _pairs_from_syvb(self, raw_rows: list[dict]) -> list[CodePair]:
        validated: list[dict] = []
        n_no_control = 0
        n_no_hack = 0
        n_bad_py = 0

        for i, r in enumerate(raw_rows):
            control = r.get("control", "").strip()
            hack = r.get("hack", "").strip()

            if not control:
                n_no_control += 1
                continue
            if not hack:
                n_no_hack += 1
                continue

            lang = _detect_language(hack)
            if lang == "python" and not _is_valid_python(hack):
                # Misclassified: likely C++ with Python-like tokens
                if "{" in hack:
                    lang = "c++"
                else:
                    n_bad_py += 1
                    continue
            # For Python pairs, control must also parse as Python —
            # some records have a C++ control paired with a Python hack.
            if lang == "python" and not _is_valid_python(control):
                lang = "c++"

            validated.append({
                "control": control,
                "hack": hack,
                "language": lang,
                "sample_id": str(i),
                "cheat_method": r.get("cheat_method", ""),
            })

        n_py = sum(1 for r in validated if r["language"] == "python")
        n_cpp = sum(1 for r in validated if r["language"] == "c++")
        n_skipped = n_no_control + n_no_hack + n_bad_py
        logger.info(
            "school-of-hacks (syvb): %d valid (%d Python TP+TN, %d C++ TP-only; "
            "%d skipped: %d no-control, %d no-hack, %d bad-python)",
            len(validated), n_py, n_cpp, n_skipped,
            n_no_control, n_no_hack, n_bad_py,
        )
        return _build_pairs(validated)

    def _pairs_from_ltr(self, raw_rows: list[dict]) -> list[CodePair]:
        """TP-only pairs from longtermrisk Arrow (control field is empty)."""
        pairs: list[CodePair] = []
        for i, r in enumerate(raw_rows):
            hack = str(r.get("school_of_reward_hacks") or "").strip()
            if not hack:
                continue
            if not ("def " in hack and "return" in hack):
                continue
            if not _is_valid_python(hack):
                continue
            original = str(r.get("user") or r.get("task") or "# no reference solution")
            pairs.append(CodePair(
                original_code=original,
                generated_code=hack,
                language="python",
                benchmark="school-of-hacks",
                category="hardcoded-test-cases",
                sample_id=f"sorh-ltr-tp-{i}",
                metadata={
                    "label": "hack",
                    "cheat_method": str(r.get("cheat_method") or ""),
                    "pair_type": "TP",
                    "source": "longtermrisk-fallback",
                },
            ))

        logger.info("school-of-hacks (ltr fallback): %d TP pairs", len(pairs))
        return pairs
