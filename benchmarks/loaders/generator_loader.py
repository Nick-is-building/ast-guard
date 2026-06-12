"""Load generator-produced JSONL samples with mandatory split enforcement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Literal

from benchmarks.loaders import BenchmarkLoader, CodePair, register

# Check-coupled categories — used for backward-compat split inference on old samples.
_COUPLED_CATEGORIES: frozenset[str] = frozenset({
    "hardcoded_outputs",
    "lookup_table",
    "eval_obfuscation",
    "forbidden_import",
    "enumeration",
    "complexity_collapse",
})


@register
class GeneratorLoader(BenchmarkLoader):
    """
    Loader for generator-produced JSONL files.

    The API enforces the calibration/eval split structurally:
      - load_calibration(path) and load_eval(path) are the safe entry points.
      - load_samples() without an explicit split raises ValueError.
      - There is deliberately no load_all() escape hatch.

    Backward compatibility: old samples without a 'split' metadata field are
    inferred conservatively — never silently promoted to 'eval'.
    """

    name = "generator"

    def download(self) -> None:
        """No-op: generator output is produced locally, not downloaded."""

    def is_available(self) -> bool:
        """Always True — availability depends on the path supplied at load time."""
        return True

    def load_samples(  # type: ignore[override]
        self,
        path: Path | str | None = None,
        split: Literal["calibration", "eval"] | None = None,
    ) -> list[CodePair]:
        """
        Load samples from a generator JSONL file.

        split is required. Omitting it raises ValueError to prevent accidental
        mixing of calibration and eval data. Prefer load_calibration(path) or
        load_eval(path) for clearer call-site intent.
        """
        if split is None:
            raise ValueError(
                "split is required — call load_calibration(path) or load_eval(path) "
                "to prevent accidental mixing of calibration and eval data."
            )
        if path is None:
            raise ValueError("path is required for GeneratorLoader.load_samples().")
        return list(self._iter_samples(Path(path), split=split))

    def load_calibration(self, path: Path | str) -> list[CodePair]:
        """Load only calibration-split samples (check-coupled hacks and TN pairs)."""
        return list(self._iter_samples(Path(path), split="calibration"))

    def load_eval(self, path: Path | str) -> list[CodePair]:
        """Load only eval-split samples (open-mode hacks)."""
        return list(self._iter_samples(Path(path), split="eval"))

    def _iter_samples(
        self,
        path: Path,
        split: Literal["calibration", "eval"],
    ) -> Iterator[CodePair]:
        if not path.exists():
            return

        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{path}:{lineno}: invalid JSON: {exc}"
                    ) from exc

                if self._infer_split(record) != split:
                    continue

                yield CodePair(
                    original_code=record.get("original_code", ""),
                    generated_code=record.get("generated_code", ""),
                    language=record.get("language", "python"),
                    benchmark="generator",
                    category=record.get("category", "unknown"),
                    sample_id=record.get("sample_id", ""),
                    metadata=record.get("metadata", {}),
                )

    @staticmethod
    def _infer_split(record: dict) -> Literal["calibration", "eval"]:
        """
        Determine the split for one JSONL record.

        Priority order:
        1. metadata['split'] — explicit field written by the generator.
        2. sample_id prefix — 'open/...' signals eval (new generator format).
        3. category in _COUPLED_CATEGORIES — calibration (backward compat).
        4. Default → calibration. Never silently promote to eval.
        """
        meta = record.get("metadata") or {}
        if "split" in meta:
            value = meta["split"]
            if value in ("calibration", "eval"):
                return value
            raise ValueError(
                f"Invalid metadata.split value {value!r}; "
                "expected 'calibration' or 'eval'."
            )

        sample_id = record.get("sample_id", "")
        if sample_id.startswith("open/"):
            return "eval"

        if record.get("category", "") in _COUPLED_CATEGORIES:
            return "calibration"

        # Unknown category, no explicit split: default to calibration.
        # eval is the privileged split — nothing drifts into it silently.
        return "calibration"
