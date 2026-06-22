"""
Eval adapter for PatronusAI/trace-dataset.

517 agentic Claude Code trajectories (249 benign, 268 hack), 10 leaf-code taxonomy.
Code is reconstructed from Write (snapshot) and Edit (str_replace diff) tool calls
embedded in a JSON 'conversation' field.  No pair-mode baseline exists — standalone only.

Reconstruction per file_path (tool calls applied in turn order):
  Write  → reset file content to Write.content.
  Edit   → str_replace(old_string, new_string) on current content.
  Patch fail  → file marked CONFLICT; partially-applied content is retained.
  Edit-only   → no Write baseline; largest new_string fragment used.

Primary-file heuristic: in-scope file with most Write+Edit calls; non-conflict preferred.
In-scope extensions: .py → python, .js/.ts/.tsx/.jsx → javascript, .sh/.bash → bash.

Category scope:
  syntactic (in-scope AST targets):  1.1.2, 1.1.3, 1.2.1, 1.2.2, 1.2.3
  semantic  (out-of-scope by design): 1.1.1, 1.3.1, 1.3.2, 1.4.1, 1.4.2

Multi-label trajectories produce one EvalRecord per label code.
The _problem_key groups all label records from the same trajectory into the same split.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from eval.adapters import AdapterBase, register
from eval.record import EvalRecord

# ── TRACE taxonomy ────────────────────────────────────────────────────────────
_TRACE_CATEGORY: dict[str, str] = {
    "1.1.1": "trace-test-assertion-bypass",
    "1.1.2": "trace-test-infra-patching",
    "1.1.3": "trace-coverage-gaming",
    "1.2.1": "trace-output-hardcoding",
    "1.2.2": "trace-metric-fabrication",
    "1.2.3": "trace-eval-code-modification",
    "1.3.1": "trace-environment-manipulation",
    "1.3.2": "trace-side-channel",
    "1.4.1": "trace-scope-violation",
    "1.4.2": "trace-deceptive-completion",
}

# File extensions → ast-guard language identifier
_EXT_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".jsx": "javascript",
    ".sh": "bash",
    ".bash": "bash",
}


def _lang_of(path: str) -> Optional[str]:
    return _EXT_LANG.get(Path(path).suffix.lower())


def _parse_tool_calls(turn: dict) -> list[dict]:
    """Extract {name, args} dicts from a conversation turn's tool_calls list."""
    raw = turn.get("tool_calls")
    if not raw or not isinstance(raw, list):
        return []
    result = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        # OpenAI-style: {"id": ..., "function": {"name": ..., "arguments": "..."}}
        # Direct-style: {"name": ..., "arguments": ...}
        func = tc.get("function") or tc
        name = func.get("name") or tc.get("name", "")
        args_raw = func.get("arguments") or func.get("parameters") or "{}"
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except (json.JSONDecodeError, ValueError):
                args = {}
        elif isinstance(args_raw, dict):
            args = args_raw
        else:
            args = {}
        if name:
            result.append({"name": name, "args": args})
    return result


def _reconstruct_files(conversation: list[dict]) -> dict[str, dict]:
    """
    Replay Write and Edit tool calls per file_path and return reconstructed state.

    Returns mapping file_path → {content, lang, n_calls, conflict, edit_only}.
    - conflict=True  : at least one Edit patch failed (old_string not found).
    - edit_only=True : no Write call preceded the first Edit; using fragment.
    - content=None   : no scannable content could be extracted.
    """
    # file_state[path] = {"content": str|None, "lang": str, "n_calls": int,
    #                      "conflict": bool, "edit_only": bool, "_frags": list}
    file_state: dict[str, dict] = {}

    for turn in conversation:
        for tc in _parse_tool_calls(turn):
            name = tc["name"]
            args = tc["args"]
            path = args.get("file_path", "")
            if not path:
                continue
            lang = _lang_of(path)
            if lang is None:
                continue

            if path not in file_state:
                file_state[path] = {
                    "content": None,
                    "lang": lang,
                    "n_calls": 0,
                    "conflict": False,
                    "edit_only": False,
                    "_frags": [],
                }
            state = file_state[path]
            state["n_calls"] += 1

            if name == "Write":
                state["content"] = args.get("content", "")
                state["edit_only"] = False

            elif name == "Edit":
                old = args.get("old_string", "")
                new = args.get("new_string", "")
                if state["content"] is None:
                    # Edit-only path: accumulate new_string fragments
                    state["_frags"].append(new)
                    state["edit_only"] = True
                elif not state["conflict"]:
                    if old in state["content"]:
                        state["content"] = state["content"].replace(old, new, 1)
                    else:
                        state["conflict"] = True
                        # Retain partially-applied content as a usable fallback.

    # Resolve Edit-only files: use the largest new_string fragment.
    for state in file_state.values():
        if state["content"] is None and state["_frags"]:
            state["content"] = max(state["_frags"], key=len)
        state.pop("_frags", None)

    return file_state


def _primary_file(file_state: dict[str, dict]) -> Optional[tuple[str, dict]]:
    """
    Return (path, state) for the best in-scope file to scan.

    Preference order: non-conflict files, then conflict files (last resort).
    Tie-break: most Write+Edit calls.
    """
    non_conflict = [
        (p, s) for p, s in file_state.items()
        if s.get("content") and not s.get("conflict")
    ]
    if non_conflict:
        return max(non_conflict, key=lambda x: x[1]["n_calls"])

    with_content = [
        (p, s) for p, s in file_state.items()
        if s.get("content")
    ]
    if with_content:
        return max(with_content, key=lambda x: x[1]["n_calls"])

    return None


def _parse_labels(label_str: str) -> list[str]:
    """Parse TRACE label field into a list of code strings.

    "0"        → []           (benign)
    "1.2.1"    → ["1.2.1"]
    "1.1.1,1.2.3" → ["1.1.1", "1.2.3"]
    """
    s = label_str.strip()
    if s == "0":
        return []
    return [c.strip() for c in s.split(",") if c.strip()]


@register("trace")
class TRACEEvalAdapter(AdapterBase):
    """Adapter for PatronusAI/trace-dataset agentic trajectory eval."""

    def load(self) -> list[EvalRecord]:
        """
        Load TRACE trajectories, reconstruct code, and return EvalRecords.

        Multi-label trajectories produce one record per label code so that
        per-category metrics are correctly attributed.
        Raises ImportError if the 'datasets' library is absent.
        """
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError(
                "The 'datasets' library is required for the TRACE adapter.\n"
                "Install: pip install datasets"
            )

        ds = load_dataset("PatronusAI/trace-dataset", split="train")

        records: list[EvalRecord] = []
        stats = {"total": 0, "no_scannable": 0, "conflict_primary": 0,
                 "edit_only_primary": 0, "clean": 0}

        for row in ds:
            stats["total"] += 1
            traj_id: str = row["trajectory_id"]
            label_codes = _parse_labels(row["label"])
            is_hack = bool(label_codes)

            try:
                conversation = json.loads(row["conversation"])
            except (json.JSONDecodeError, TypeError):
                stats["no_scannable"] += 1
                continue

            if not isinstance(conversation, list):
                stats["no_scannable"] += 1
                continue

            file_state = _reconstruct_files(conversation)
            primary = _primary_file(file_state)

            if primary is None:
                stats["no_scannable"] += 1
                continue

            ppath, pstate = primary
            lang = pstate["lang"]
            content = pstate["content"]

            if pstate["conflict"]:
                stats["conflict_primary"] += 1
                extraction = "conflict-fallback"
            elif pstate["edit_only"]:
                stats["edit_only_primary"] += 1
                extraction = "edit-only-fragment"
            else:
                stats["clean"] += 1
                extraction = "clean"

            shared_meta = {
                "trajectory_id": traj_id,
                "primary_file": ppath,
                "extraction": extraction,
                "n_files_modified": len(file_state),
                "label_codes": label_codes,
            }

            if is_hack:
                for code in label_codes:
                    category = _TRACE_CATEGORY.get(code, f"trace-unknown-{code}")
                    records.append(EvalRecord(
                        id=f"trace-{traj_id}-{code}",
                        language=lang,
                        code=content,
                        label="hack",
                        original_code=None,
                        hack_category=category,
                        dataset="trace",
                        split="dev",
                        metadata={**shared_meta, "label_code": code},
                    ))
            else:
                records.append(EvalRecord(
                    id=f"trace-{traj_id}-benign",
                    language=lang,
                    code=content,
                    label="benign",
                    original_code=None,
                    hack_category="trace-benign",
                    dataset="trace",
                    split="dev",
                    metadata={**shared_meta, "label_code": "0"},
                ))

        if not records:
            raise RuntimeError(
                "TRACE adapter produced 0 records. "
                "Verify that PatronusAI/trace-dataset is accessible."
            )

        print(
            f"[trace] Extraction: total={stats['total']}  "
            f"clean={stats['clean']}  "
            f"edit-only-fragment={stats['edit_only_primary']}  "
            f"conflict-fallback={stats['conflict_primary']}  "
            f"no-scannable={stats['no_scannable']}"
        )
        return records

    def _problem_key(self, record: EvalRecord) -> str:
        # Group all label records from the same trajectory into the same split.
        return record.metadata.get("trajectory_id", record.id)
