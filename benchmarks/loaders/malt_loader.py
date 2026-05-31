"""
Loader for the MALT (METR Agent Labeling Track) benchmark.

Dataset: ~/.ast-guard/benchmarks/malt-public/malt_code_samples.json
140,726 code blocks from METR's MALT dataset spanning 7,179 agent transcripts
and 21 models. Labels describe agent behavior: normal, bypass_constraints,
hardcoded_solution, sabotage, partial_problem_solving, ignores_task_instructions,
match_weaker_model, refusals, reasoning_about_task, gives_up.

Each CodePair has original_code="" and metadata["standalone"]=True because only
the agent's output is available. Use scan_standalone() instead of scan().
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_DATA_FILE = "malt_code_samples.json"
_MIN_CODE_LEN = 50


def _primary_label(labels: list[str]) -> str:
    """Return the most specific non-normal label, or 'normal' if only normal."""
    non_normal = [lbl for lbl in labels if lbl != "normal"]
    return non_normal[0] if non_normal else "normal"


def _detect_language(code: str) -> str:
    """Detect language, defaulting to 'python' when uncertain."""
    try:
        from ast_guard.multilang import detect_language
        lang = detect_language(code)
        return lang if lang != "unknown" else "python"
    except Exception:
        return "python"


def _parse_ok(code: str, language: str) -> bool:
    """Return True if code parses without error."""
    if language == "python":
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False
    # For bash/javascript, attempt tree-sitter parse if available.
    try:
        from ast_guard.multilang import extract_metrics_multilang
        extract_metrics_multilang(code, language)
        return True
    except ImportError:
        return True  # multilang extras not installed — accept the sample
    except Exception:
        return False


@register
class MaltLoader(BenchmarkLoader):
    """Loader for the METR MALT agent transcript benchmark."""

    name = "malt"

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            data_dir = Path.home() / ".ast-guard" / "benchmarks" / "malt-public"
        super().__init__(data_dir)

    def download(self) -> None:
        logger.info(
            "MALT data must be placed manually at %s/%s — "
            "no automatic download available.",
            self.data_dir,
            _DATA_FILE,
        )

    def is_available(self) -> bool:
        return (self.data_dir / _DATA_FILE).exists()

    def load_samples(self) -> list[CodePair]:
        if not self.is_available():
            raise FileNotFoundError(
                f"MALT data not found at {self.data_dir / _DATA_FILE}. "
                "Place malt_code_samples.json in that directory."
            )

        path = self.data_dir / _DATA_FILE
        logger.info("Loading MALT data from %s …", path)
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)

        pairs: list[CodePair] = []
        skipped_short = 0
        skipped_parse = 0

        for entry in raw:
            code = entry.get("code", "")
            if len(code) < _MIN_CODE_LEN:
                skipped_short += 1
                continue

            labels = entry.get("labels") or ["normal"]
            language = _detect_language(code)

            if not _parse_ok(code, language):
                skipped_parse += 1
                continue

            category = _primary_label(labels)
            pairs.append(CodePair(
                original_code="",
                generated_code=code,
                language=language,
                benchmark="malt",
                category=category,
                sample_id=str(entry.get("row_index", len(pairs))),
                metadata={
                    "labels": labels,
                    "task": entry.get("task", ""),
                    "model": entry.get("model", ""),
                    "standalone": True,
                },
            ))

        logger.info(
            "malt: loaded %d samples (skipped %d too-short, %d parse failures)",
            len(pairs), skipped_short, skipped_parse,
        )
        return pairs
