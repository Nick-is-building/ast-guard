"""
Loader for the TRACE dataset (Deshpande et al., 2026).

Expects data in ~/.ast-guard/benchmarks/trace-dataset/ (manual download
required — the dataset is gated on HuggingFace and needs a logged-in user).

Format: ChatML JSON files — 517 multi-turn trajectories, 268 hacked and
249 benign, covering 54 subcategories across 10 major TRACE categories.
We extract code blocks from assistant turns and pair them with the original
code from the task setup.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z]*)\n(?P<body>.*?)```", re.DOTALL)


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    return [
        (m.group("lang") or "unknown", m.group("body").strip())
        for m in _CODE_FENCE.finditer(text)
    ]


def _get_text(msg: dict) -> str:
    """Return the plain text of a ChatML message regardless of content shape."""
    content = msg.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("value") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(filter(None, parts))
    return ""


def _parse_chatml(data: dict | list, path: Path) -> list[CodePair]:
    """Parse a single TRACE ChatML record into CodePair objects."""
    records = data if isinstance(data, list) else [data]
    pairs: list[CodePair] = []

    for idx, rec in enumerate(records):
        messages = rec.get("messages") or rec.get("conversation") or []
        if not messages:
            continue

        is_hacked = bool(rec.get("is_hacked") or rec.get("hacked") or rec.get("reward_hack"))
        category = rec.get("category") or rec.get("major_category") or "unknown"
        subcategory = rec.get("subcategory") or rec.get("sub_category") or ""
        sample_id = rec.get("id") or rec.get("sample_id") or f"{path.stem}-{idx}"
        language = rec.get("language") or "python"

        # Original code lives in the first user / system message (task setup).
        original_code = ""
        agent_code_blocks: list[tuple[str, str]] = []

        for msg in messages:
            role = msg.get("role", "")
            text = _get_text(msg)

            if role in ("user", "system") and not original_code:
                blocks = _extract_code_blocks(text)
                if blocks:
                    original_code = blocks[0][1]

            if role == "assistant":
                agent_code_blocks.extend(_extract_code_blocks(text))

        if not agent_code_blocks:
            continue

        generated_code = "\n\n".join(body for _, body in agent_code_blocks)
        if not original_code:
            original_code = "# no original code in task"

        # Prefer explicit language tag from the first assistant block.
        if agent_code_blocks[0][0] in ("python", "bash", "javascript"):
            language = agent_code_blocks[0][0]
        else:
            from ast_guard.multilang import detect_language
            language = detect_language(generated_code) or language

        sid = str(sample_id) if idx == 0 else f"{sample_id}-{idx}"
        pairs.append(CodePair(
            original_code=original_code,
            generated_code=generated_code,
            language=language,
            benchmark="trace",
            category=category,
            sample_id=sid,
            metadata={
                "is_hacked": is_hacked,
                "subcategory": subcategory,
                "source_file": path.name,
            },
        ))

    return pairs


@register
class TraceLoader(BenchmarkLoader):
    """Loader for the gated TRACE reward-hacking trajectory dataset."""

    name = "trace"

    def download(self) -> None:
        """TRACE requires manual download (gated HuggingFace dataset)."""
        logger.warning(
            "TRACE dataset requires manual download.\n"
            "  1. Log in to HuggingFace: huggingface-cli login\n"
            "  2. Accept terms at https://huggingface.co/datasets/trace-dataset\n"
            "  3. Download and extract to: %s",
            self.data_dir,
        )

    def load_samples(self) -> list[CodePair]:
        """Load ChatML JSON files from self.data_dir."""
        if not self.is_available():
            raise FileNotFoundError(
                f"TRACE data not found at {self.data_dir}. "
                "Manual download required — see loader.download() for instructions."
            )

        pairs: list[CodePair] = []
        json_files = sorted(self.data_dir.rglob("*.json"))
        jsonl_files = sorted(self.data_dir.rglob("*.jsonl"))

        for path in json_files:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping %s: %s", path.name, exc)
                continue
            pairs.extend(_parse_chatml(raw, path))

        for path in jsonl_files:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping line in %s: %s", path.name, exc)
                    continue
                pairs.extend(_parse_chatml(rec, path))

        logger.info("trace: loaded %d samples", len(pairs))
        return pairs
