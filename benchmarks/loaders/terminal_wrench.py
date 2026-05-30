"""
Loader for the Terminal Wrench benchmark.

Clones https://github.com/few-sh/terminal-wrench and parses trajectory JSON
files. Each trajectory captures an agent session where tool calls contain
bash commands or code blocks; we extract those as generated_code and use
the task description as context.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)

_REPO_URL = "https://github.com/few-sh/terminal-wrench"

# Fenced code block extractor — captures language tag and body.
_CODE_FENCE = re.compile(
    r"```(?P<lang>[a-zA-Z]*)\n(?P<body>.*?)```",
    re.DOTALL,
)

_CATEGORY_MAP = {
    "hollow": "hollow-implementation",
    "hollow-implementation": "hollow-implementation",
    "output": "output-spoofing",
    "output-spoofing": "output-spoofing",
    "loophole": "constraint-loophole",
    "constraint-loophole": "constraint-loophole",
    "structural": "structural-extraction",
    "structural-extraction": "structural-extraction",
}


def _norm_category(raw: str) -> str:
    key = raw.lower().replace("_", "-").replace(" ", "-")
    return _CATEGORY_MAP.get(key, raw)


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Return list of (language, code) pairs found in fenced blocks."""
    return [
        (m.group("lang") or "unknown", m.group("body").strip())
        for m in _CODE_FENCE.finditer(text)
    ]


def _detect_lang(code: str, hint: str = "") -> str:
    from ast_guard.multilang import detect_language
    if hint in ("python", "bash", "javascript"):
        return hint
    return detect_language(code)


def _tool_calls_from_step(step: dict) -> list[dict]:
    """Normalise a trajectory step into a list of tool-call dicts."""
    # Handle both {"tool_calls": [...]} and {"tool_use": {...}} shapes.
    calls = step.get("tool_calls") or step.get("tool_use") or []
    if isinstance(calls, dict):
        calls = [calls]
    return calls


def _parse_trajectory(path: Path, sample_id: str) -> list[CodePair]:
    """Parse a single trajectory JSON file into zero or more CodePairs."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Skipping %s: %s", path.name, exc)
        return []

    # Accept both single-trajectory objects and lists of trajectories.
    records = data if isinstance(data, list) else [data]
    pairs: list[CodePair] = []

    for idx, rec in enumerate(records):
        task = rec.get("task") or rec.get("problem") or rec.get("description", "")
        raw_category = rec.get("category") or rec.get("type") or "unknown"
        category = _norm_category(raw_category)
        is_hack = bool(rec.get("is_hack") or rec.get("hack") or rec.get("exploit"))

        # Gather all code produced by the agent in tool calls / messages.
        code_snippets: list[tuple[str, str]] = []
        steps = rec.get("trajectory") or rec.get("steps") or rec.get("messages") or []
        for step in steps:
            role = step.get("role", "")
            content = step.get("content") or ""

            # Extract fenced code from message bodies.
            if content:
                code_snippets.extend(_extract_code_blocks(content))

            # Extract code from tool-call inputs.
            for call in _tool_calls_from_step(step):
                inp = call.get("input") or call.get("arguments") or call.get("params") or {}
                if isinstance(inp, str):
                    code_snippets.extend(_extract_code_blocks(inp))
                    if not _CODE_FENCE.search(inp):
                        # Plain shell command — treat as bash.
                        code_snippets.append(("bash", inp.strip()))
                elif isinstance(inp, dict):
                    cmd = inp.get("command") or inp.get("code") or inp.get("script") or ""
                    if cmd:
                        lang = call.get("type") or call.get("name") or ""
                        code_snippets.append((lang, cmd.strip()))

        if not code_snippets:
            continue

        # Use task description as original_code surrogate (captures intent).
        original_code = task if task else "# no task description"
        generated_code = "\n\n".join(body for _, body in code_snippets)
        lang = _detect_lang(generated_code, code_snippets[0][0])
        sid = f"{sample_id}-{idx}" if idx > 0 else sample_id

        pairs.append(CodePair(
            original_code=original_code,
            generated_code=generated_code,
            language=lang,
            benchmark="terminal-wrench",
            category=category,
            sample_id=sid,
            metadata={
                "is_hack": is_hack,
                "source_file": path.name,
                "raw_category": raw_category,
            },
        ))

    return pairs


@register
class TerminalWrenchLoader(BenchmarkLoader):
    """Loader for the Terminal Wrench agent-trajectory benchmark."""

    name = "terminal-wrench"

    def download(self) -> None:
        """Clone or update the Terminal Wrench repo."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        git_dir = self.data_dir / ".git"
        if git_dir.exists():
            logger.info("Updating terminal-wrench repo …")
            subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=self.data_dir,
                check=True,
                capture_output=True,
            )
        else:
            logger.info("Cloning terminal-wrench …")
            subprocess.run(
                ["git", "clone", "--depth", "1", _REPO_URL, str(self.data_dir)],
                check=True,
                capture_output=True,
            )

    def load_samples(self) -> list[CodePair]:
        """Walk all JSON files under data_dir and return CodePair records."""
        if not self.is_available():
            raise FileNotFoundError(
                f"Terminal Wrench data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        pairs: list[CodePair] = []
        json_files = sorted(self.data_dir.rglob("*.json"))
        if not json_files:
            logger.warning("No JSON files found under %s", self.data_dir)

        for path in json_files:
            sample_id = path.stem
            pairs.extend(_parse_trajectory(path, sample_id))

        logger.info("terminal-wrench: loaded %d samples", len(pairs))
        return pairs
