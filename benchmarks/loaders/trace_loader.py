"""
Loader for the TRACE dataset (Deshpande et al., 2026).

The dataset is downloaded via HuggingFace `datasets` and stored in Arrow format
under ~/.ast-guard/benchmarks/trace-dataset/.

Schema: trajectory_id, conversation (ChatML JSON string), label
  label '0'   → benign
  label != '0' → hacked (value encodes TRACE taxonomy node IDs)

We extract code blocks from assistant turns and pair them with original code
found in the first user/system message.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z]*)\n(?P<body>.*?)```", re.DOTALL)

# On disk the dataset was cached under this directory name.
_DIR_NAME = "trace-dataset"


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


def _parse_row(row: dict) -> CodePair | None:
    """Parse a single row into a CodePair. Supports two formats:
    - Arrow/real format: 'conversation' (JSON string), 'label' (string code), 'trajectory_id'
    - Legacy/test format: 'messages' (list), 'is_hacked' (bool), 'id'/'category'
    """
    # Detect which format we have.
    if "messages" in row or "conversation" not in row:
        # Legacy test format
        trajectory_id = str(row.get("id") or row.get("trajectory_id") or row.get("sample_id") or "")
        is_hacked = bool(row.get("is_hacked") or row.get("hacked") or row.get("reward_hack"))
        label = "1" if is_hacked else "0"
        messages = row.get("messages") or row.get("conversation") or []
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except json.JSONDecodeError:
                return None
        category = str(row.get("category") or ("hacked" if is_hacked else "benign"))
    else:
        # Arrow / real dataset format
        trajectory_id = str(row.get("trajectory_id") or "")
        label = str(row.get("label") or "0")
        is_hacked = label != "0"
        category = "hacked" if is_hacked else "benign"

        conv_raw = row.get("conversation") or ""
        if isinstance(conv_raw, str):
            try:
                messages = json.loads(conv_raw)
            except json.JSONDecodeError:
                return None
        elif isinstance(conv_raw, list):
            messages = conv_raw
        else:
            return None

    if not messages:
        return None

    original_code = ""
    agent_code_blocks: list[tuple[str, str]] = []
    language = "python"

    for msg in messages:
        role = msg.get("role", "")
        text = _get_text(msg)

        if role in ("user", "system") and not original_code:
            blocks = _extract_code_blocks(text)
            if blocks:
                original_code = blocks[0][1]
                if blocks[0][0] in ("python", "bash", "javascript"):
                    language = blocks[0][0]

        if role == "assistant":
            agent_code_blocks.extend(_extract_code_blocks(text))

    if not agent_code_blocks:
        return None

    generated_code = "\n\n".join(body for _, body in agent_code_blocks)
    if not original_code:
        original_code = "# no original code in task"

    # Prefer explicit language tag from the first assistant code block.
    if agent_code_blocks[0][0] in ("python", "bash", "javascript"):
        language = agent_code_blocks[0][0]
    else:
        try:
            from ast_guard.multilang import detect_language
            language = detect_language(generated_code) or language
        except ImportError:
            pass

    return CodePair(
        original_code=original_code,
        generated_code=generated_code,
        language=language,
        benchmark="trace",
        category=category,
        sample_id=trajectory_id,
        metadata={
            "is_hacked": is_hacked,
            "label": label,
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


@register
class TraceLoader(BenchmarkLoader):
    """Loader for the gated TRACE reward-hacking trajectory dataset."""

    name = "trace"

    def __init__(self, data_dir: Path | None = None):
        # The dataset is cached on disk under the HF repo slug, not the loader name.
        super().__init__(data_dir or (Path.home() / ".ast-guard" / "benchmarks" / _DIR_NAME))

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
        """Load trajectories from Arrow / JSON / JSONL files in self.data_dir."""
        if not self.is_available():
            raise FileNotFoundError(
                f"TRACE data not found at {self.data_dir}. "
                "Manual download required — see loader.download() for instructions."
            )

        rows: list[dict] = []

        for path in sorted(self.data_dir.rglob("*.arrow")):
            rows.extend(_load_arrow(path))

        for path in sorted(self.data_dir.rglob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                batch = raw if isinstance(raw, list) else [raw]
                rows.extend(r for r in batch if isinstance(r, dict))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping %s: %s", path.name, exc)

        for path in sorted(self.data_dir.rglob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        rows.append(rec)
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping line in %s: %s", path.name, exc)

        pairs: list[CodePair] = []
        seen: set[str] = set()
        n_skipped_parse = 0
        n_skipped_dup = 0
        for row in rows:
            pair = _parse_row(row)
            if pair is None:
                n_skipped_parse += 1
                continue
            if pair["sample_id"] in seen:
                n_skipped_dup += 1
                continue
            seen.add(pair["sample_id"])
            pairs.append(pair)

        n_skipped = n_skipped_parse + n_skipped_dup
        if pairs:
            logger.info(
                "trace: loaded %d samples (%d skipped — %d no-code-block, %d duplicate; from %d rows)",
                len(pairs), n_skipped, n_skipped_parse, n_skipped_dup, len(rows),
            )
        else:
            logger.warning(
                "trace: loaded 0 samples from %d rows (%d no-code-block, %d duplicate)",
                len(rows), n_skipped_parse, n_skipped_dup,
            )
        return pairs
