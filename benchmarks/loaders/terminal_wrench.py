"""
Loader for the Terminal Wrench benchmark.

Reads ~/.ast-guard/benchmarks/terminal-wrench/index/ which contains:
  tasks.json        — per-task metadata with baseline info
  trajectories.json — per-trajectory metadata with exploit descriptions

The public release does not include the raw agent transcripts, so we compose a
synthetic CodePair from available fields:
  original_code = task description (from baseline label)
  generated_code = exploit summary + key hack steps (from hacked trajectories)

Only "rewarded_serious_exploit" trajectories are included as hacked samples;
"attacker_legitimate_solve" trajectories are used as benign pairs.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

_CODE_FENCE = re.compile(r"```(?P<lang>[a-zA-Z]*)\n(?P<body>.*?)```", re.DOTALL)
_CODE_FENCE_RE = _CODE_FENCE

logger = logging.getLogger(__name__)

_REPO_URL = "https://github.com/few-sh/terminal-wrench"

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
    return _CATEGORY_MAP.get(key, raw or "unknown")


def _extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """Return list of (language, code) pairs found in fenced blocks."""
    return [
        (m.group("lang") or "unknown", m.group("body").strip())
        for m in _CODE_FENCE.finditer(text)
    ]


def _detect_lang(code: str, hint: str = "") -> str:
    if hint in ("python", "bash", "javascript"):
        return hint
    try:
        from ast_guard.multilang import detect_language
        return detect_language(code)
    except ImportError:
        return "unknown"


def _tool_calls_from_step(step: dict) -> list[dict]:
    """Normalise a trajectory step into a list of tool-call dicts."""
    calls = step.get("tool_calls") or step.get("tool_use") or []
    if isinstance(calls, dict):
        calls = [calls]
    return calls


def _parse_trajectory(path: Path, sample_id: str) -> list[CodePair]:
    """Parse a legacy trajectory JSON file into zero or more CodePairs."""
    try:
        data = _load_json(path)
    except Exception as exc:
        logger.warning("Skipping %s: %s", path.name, exc)
        return []
    if data is None:
        return []

    records = data if isinstance(data, list) else [data]
    pairs: list[CodePair] = []

    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        task = rec.get("task") or rec.get("problem") or rec.get("description", "")
        raw_category = rec.get("category") or rec.get("type") or "unknown"
        category = _norm_category(raw_category)
        is_hack = bool(rec.get("is_hack") or rec.get("hack") or rec.get("exploit"))

        code_snippets: list[tuple[str, str]] = []
        steps = rec.get("trajectory") or rec.get("steps") or rec.get("messages") or []
        for step in steps:
            role = step.get("role", "")
            content = step.get("content") or ""
            if content:
                code_snippets.extend(_extract_code_blocks(content))
            for call in _tool_calls_from_step(step):
                inp = call.get("input") or call.get("arguments") or call.get("params") or {}
                if isinstance(inp, str):
                    code_snippets.extend(_extract_code_blocks(inp))
                    if not _CODE_FENCE_RE.search(inp):
                        code_snippets.append(("bash", inp.strip()))
                elif isinstance(inp, dict):
                    cmd = inp.get("command") or inp.get("code") or inp.get("script") or ""
                    if cmd:
                        lang = call.get("type") or call.get("name") or ""
                        code_snippets.append((lang, cmd.strip()))

        if not code_snippets:
            continue

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


def _load_json(path: Path) -> list | dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def _build_task_map(tasks: list[dict]) -> dict[str, dict]:
    """Return {task_id: task_record} for quick lookup."""
    return {str(t.get("task_id", "")): t for t in tasks if isinstance(t, dict)}


def _make_pair_from_trajectory(traj: dict, task_map: dict[str, dict]) -> CodePair | None:
    """Build a CodePair from a trajectory metadata record."""
    classification = str(traj.get("classification") or "")
    is_hack = traj.get("judged_serious_exploit") or classification == "rewarded_serious_exploit"
    is_legit = traj.get("judged_legitimate_solve") or classification == "attacker_legitimate_solve"

    if not is_hack and not is_legit:
        return None

    task_id = str(traj.get("task_id") or "")
    task = task_map.get(task_id, {})
    baseline = task.get("baseline") or {}

    # Use the baseline label as the task description / original code surrogate.
    original_code = str(baseline.get("label") or task.get("description") or "# task description not available").strip()
    if not original_code:
        original_code = "# task description not available"

    if is_hack:
        # Compose a pseudo-code representation from the exploit metadata.
        summary = str(traj.get("brief_exploit_summary") or "")
        explanation = str(traj.get("explanation") or "")
        key_steps = traj.get("key_hack_steps") or []
        if isinstance(key_steps, list):
            key_steps_text = "\n".join(f"# {step}" for step in key_steps if step)
        else:
            key_steps_text = f"# {key_steps}"

        parts = []
        if summary:
            parts.append(f"# Exploit: {summary}")
        if key_steps_text:
            parts.append(key_steps_text)
        if explanation:
            parts.append(f"# Explanation: {explanation[:500]}")
        generated_code = "\n".join(parts) if parts else "# no exploit details available"
        category = "exploit"
    else:
        generated_code = original_code
        category = "legitimate"

    # Infer category from observed_categories if available.
    observed = traj.get("observed_categories") or []
    if observed and isinstance(observed, list):
        category = _norm_category(str(observed[0]))

    run_name = str(traj.get("run_name") or "")
    sample_id = f"{task_id}-{traj.get('trajectory_label', '')}-{traj.get('attempt_index_before_fixer', 0)}"

    return CodePair(
        original_code=original_code,
        generated_code=generated_code,
        language="bash",
        benchmark="terminal-wrench",
        category=category,
        sample_id=sample_id,
        metadata={
            "is_hack": bool(is_hack),
            "classification": classification,
            "model": str(traj.get("model") or ""),
            "run_name": run_name,
        },
    )


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
        """Load samples from either the index format or legacy trajectory JSON files."""
        if not self.is_available():
            raise FileNotFoundError(
                f"Terminal Wrench data not found at {self.data_dir}. "
                "Run with --download or call loader.download()."
            )

        index_dir = self.data_dir / "index"
        trajectories_path = index_dir / "trajectories.json"

        if trajectories_path.exists():
            pairs = self._load_from_index(index_dir, trajectories_path)
        else:
            pairs = self._load_from_trajectory_files()
        if not pairs:
            logger.warning(
                "terminal-wrench: loaded 0 samples — check data directory %s", self.data_dir
            )
        return pairs

    def _load_from_index(self, index_dir: Path, trajectories_path: Path) -> list[CodePair]:
        """Load from index/trajectories.json (real dataset format)."""
        trajectories_raw = _load_json(trajectories_path)
        if not isinstance(trajectories_raw, list):
            logger.warning("terminal-wrench: unexpected format in trajectories.json")
            return []

        tasks_path = index_dir / "tasks.json"
        task_map: dict[str, dict] = {}
        if tasks_path.exists():
            tasks_raw = _load_json(tasks_path)
            if isinstance(tasks_raw, list):
                task_map = _build_task_map(tasks_raw)

        pairs: list[CodePair] = []
        seen: set[str] = set()
        n_skipped = 0
        for traj in trajectories_raw:
            if not isinstance(traj, dict):
                n_skipped += 1
                continue
            pair = _make_pair_from_trajectory(traj, task_map)
            if pair is None:
                n_skipped += 1
                continue
            if pair["sample_id"] in seen:
                n_skipped += 1
                continue
            seen.add(pair["sample_id"])
            pairs.append(pair)

        logger.info(
            "terminal-wrench: loaded %d samples from index (%d skipped — not hack/legit or duplicate)",
            len(pairs), n_skipped,
        )
        return pairs

    def _load_from_trajectory_files(self) -> list[CodePair]:
        """Load from legacy trajectory JSON files (test / custom data format)."""
        pairs: list[CodePair] = []
        json_files = sorted(self.data_dir.rglob("*.json"))
        if not json_files:
            logger.warning("No JSON files found under %s", self.data_dir)
            return pairs

        for path in json_files:
            sample_id = path.stem
            pairs.extend(_parse_trajectory(path, sample_id))

        logger.info(
            "terminal-wrench: loaded %d samples from %d trajectory files",
            len(pairs), len(json_files),
        )
        return pairs
