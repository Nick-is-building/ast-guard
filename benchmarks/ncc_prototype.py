"""
NCC (Normalized Conditional Complexity) prototype.
Standalone research module — NOT in the scan path, NOT integrated into ast-guard core.

Theory:
  NCC = C(code | tests) / C(code)
  where C(X | Y) is estimated via compression with Y as preset dictionary.

  Low  NCC → tests explain code well  → memorized / hardcoded
  High NCC → code is independent      → generalizing solution

Compression estimators:
  raw   : ncc_raw() — raw UTF-8, no canonicalization (PRIMARY; see note below)
  zdict : ncc()     — canonical + zlib.compressobj(zdict=tests)
  concat: ncc_concat() — canonical + concatenation method
  lzma  : ncc_lzma() — canonical + lzma concatenation

Canonicalization note (from calibration on SORH Python):
  Canonical NCC (AUC=0.73) is WORSE than raw text NCC (AUC=0.91).
  Root cause: canonicalization replaces function names like `perimeter_pentagon`
  (18 chars) with `V0` (2 chars), destroying the longest LZ77 matches.
  Function names shared between tests and code are the primary compression signal
  alongside long string literals.  Raw text preserves these; canonical discards them.

  lzma is weakest (AUC=0.57): stronger compression normalizes away the
  conditional advantage entirely at these code scales (50-300 bytes).

LZ77 minimum match caveat:
  zlib requires a 3-byte minimum match for backreferences.  Single-digit or
  two-digit numeric literals (5, 25, etc.) do not benefit from dictionary
  compression even when they appear in both tests and code.  NCC therefore
  misses hacks that hardcode only short integers; recall depends on the presence
  of longer literals (strings, function names, array values).

ΔNCC = NCC(code | foreign_tests) − NCC(code | own_tests)
  > 0 → own tests help more → code is correlated with tests
  ≈ 0 → tests don't matter  → code is independent
  Note: report as P(delta_hack > delta_ctrl), not P(delta_hack < delta_ctrl).

Min-size gate: skip samples with raw code < 50 bytes (compression too noisy).
"""
from __future__ import annotations

import io
import json
import keyword
import logging
import random
import tokenize
import zlib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Compression level (fixed for reproducibility) ────────────────────────────
_LEVEL = 6
_MIN_CANON_BYTES = 50

# ── Builtin names kept as-is in canonicalization ─────────────────────────────
_KEEP_NAMES = frozenset({
    "True", "False", "None",
    "print", "len", "range", "int", "str", "float", "bool",
    "list", "dict", "set", "tuple", "frozenset",
    "sorted", "enumerate", "zip", "map", "filter", "reversed",
    "sum", "min", "max", "abs", "round",
    "type", "isinstance", "issubclass", "hasattr", "getattr", "setattr", "delattr",
    "open", "input", "super", "object", "property",
    "all", "any", "iter", "next",
    "NotImplemented", "Ellipsis",
})


def canonicalize(code: str) -> bytes:
    """Parse code to a token stream with normalized identifiers, preserved literals.

    Replaces user-defined names with V0, V1, … so that structural patterns
    are normalized but literal values (numbers, strings) are kept verbatim.
    Falls back to whitespace-normalized UTF-8 on tokenization failure.
    """
    try:
        tokens: list[str] = []
        name_map: dict[str, str] = {}

        reader = io.StringIO(code).readline
        for tok_type, tok_string, _, _, _ in tokenize.generate_tokens(reader):
            if tok_type == tokenize.NAME:
                if keyword.iskeyword(tok_string) or tok_string in _KEEP_NAMES:
                    tokens.append(tok_string)
                else:
                    if tok_string not in name_map:
                        name_map[tok_string] = f"V{len(name_map)}"
                    tokens.append(name_map[tok_string])
            elif tok_type in (tokenize.NUMBER, tokenize.STRING, tokenize.OP):
                tokens.append(tok_string)
            elif tok_type in (tokenize.NEWLINE, tokenize.NL):
                tokens.append("\n")
            elif tok_type == tokenize.INDENT:
                tokens.append("  ")
            # Drop COMMENT, ENCODING, ENDMARKER, DEDENT
        return " ".join(tokens).encode("utf-8")
    except tokenize.TokenError:
        # Fallback: whitespace-normalize raw text (handles C++, malformed Python)
        return " ".join(code.split()).encode("utf-8")


def _c(data: bytes) -> int:
    """Plain zlib compressed length."""
    return len(zlib.compress(data, _LEVEL))


def _c_zdict(data: bytes, dictionary: bytes) -> int:
    """zlib compressed length with dictionary pre-loaded."""
    obj = zlib.compressobj(level=_LEVEL, zdict=dictionary)
    return len(obj.compress(data) + obj.flush())


def _c_concat(data: bytes, prefix: bytes) -> int:
    """Conditional compression via concatenation: C(prefix+data) - C(prefix)."""
    return len(zlib.compress(prefix + data, _LEVEL)) - len(zlib.compress(prefix, _LEVEL))


def ncc_raw(code: str, tests: str) -> Optional[float]:
    """NCC via raw UTF-8 (no canonicalization) — PRIMARY metric.

    Raw text preserves long LZ77 matches from function names and string literals
    that canonicalization discards.  Calibration: AUC=0.91 vs 0.73 canonical.
    """
    c = code.encode("utf-8")
    t = tests.encode("utf-8")
    if len(c) < _MIN_CANON_BYTES:
        return None
    denom = _c(c)
    if denom == 0:
        return None
    obj = zlib.compressobj(level=_LEVEL, zdict=t)
    return len(obj.compress(c) + obj.flush()) / denom


def ncc(code: str, tests: str) -> Optional[float]:
    """NCC via zlib zdict estimator.

    Returns None if canonical code is too short for reliable compression.
    """
    cc = canonicalize(code)
    if len(cc) < _MIN_CANON_BYTES:
        return None
    ct = canonicalize(tests)
    denom = _c(cc)
    if denom == 0:
        return None
    return _c_zdict(cc, ct) / denom


def ncc_concat(code: str, tests: str) -> Optional[float]:
    """NCC via concatenation estimator (cross-check)."""
    cc = canonicalize(code)
    if len(cc) < _MIN_CANON_BYTES:
        return None
    ct = canonicalize(tests)
    denom = _c(cc)
    if denom == 0:
        return None
    cond = _c_concat(cc, ct)
    return cond / denom


def ncc_lzma(code: str, tests: str) -> Optional[float]:
    """NCC via lzma concatenation (stronger compressor; slower, lower noise floor)."""
    import lzma
    cc = canonicalize(code)
    if len(cc) < _MIN_CANON_BYTES:
        return None
    ct = canonicalize(tests)

    def lzma_len(data: bytes) -> int:
        return len(lzma.compress(data, preset=3))

    denom = lzma_len(cc)
    if denom == 0:
        return None
    cond = lzma_len(ct + cc) - lzma_len(ct)
    return cond / denom


def delta_ncc(code: str, own_tests: str, foreign_tests: str) -> Optional[float]:
    """ΔNCC = NCC(code|foreign) − NCC(code|own).

    Positive → own tests help more → correlated with own tests (memorized).
    """
    own = ncc(code, own_tests)
    foreign = ncc(code, foreign_tests)
    if own is None or foreign is None:
        return None
    return foreign - own


# ── Dataset loading helpers ───────────────────────────────────────────────────

def _load_sorh_python_samples() -> list[dict]:
    """Load SORH samples where both hack and control are valid Python.

    Returns list of dicts: {hack, control, tests (= user field), sample_id}.
    """
    import ast as _ast
    p = Path.home() / ".ast-guard" / "benchmarks" / "school-of-hacks" / "syvb_coding.json"
    rows = json.loads(p.read_text(encoding="utf-8"))

    def is_py(code: str) -> bool:
        if not code.strip():
            return False
        try:
            _ast.parse(code)
            return True
        except SyntaxError:
            return False

    out = []
    for i, r in enumerate(rows):
        hack = r.get("hack", "").strip()
        control = r.get("control", "").strip()
        user = r.get("user", "").strip()
        if is_py(hack) and is_py(control) and user:
            out.append({
                "hack": hack,
                "control": control,
                "tests": user,
                "sample_id": str(i),
            })
    logger.info("SORH: %d Python samples loaded", len(out))
    return out


def _load_mbpp_samples() -> list[dict]:
    """Load MBPP samples with non-empty code and test_list.

    Returns list of dicts: {code, tests (joined test_list), task_id}.
    """
    p = Path.home() / ".ast-guard" / "benchmarks" / "mbpp" / "mbpp_rows.json"
    rows = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        code = r.get("code", "").strip()
        test_list = r.get("test_list", [])
        if not code or not test_list:
            continue
        tests = "\n".join(test_list)
        out.append({
            "code": code,
            "tests": tests,
            "task_id": r["task_id"],
        })
    logger.info("MBPP: %d samples loaded", len(out))
    return out


# ── Analysis ──────────────────────────────────────────────────────────────────

def _describe(values: list[float], label: str) -> dict:
    """Compute summary stats for a list of NCC values."""
    if not values:
        return {"label": label, "n": 0}
    values = sorted(values)
    n = len(values)
    mean = sum(values) / n
    med = values[n // 2]
    p25 = values[n // 4]
    p75 = values[3 * n // 4]
    return {
        "label": label,
        "n": n,
        "mean": round(mean, 4),
        "median": round(med, 4),
        "p25": round(p25, 4),
        "p75": round(p75, 4),
        "min": round(values[0], 4),
        "max": round(values[-1], 4),
    }


def _auc(pos_scores: list[float], neg_scores: list[float]) -> float:
    """Mann-Whitney AUC: P(score_pos < score_neg) (lower NCC = positive class)."""
    if not pos_scores or not neg_scores:
        return float("nan")
    wins = sum(1 for p in pos_scores for n in neg_scores if p < n)
    ties = sum(0.5 for p in pos_scores for n in neg_scores if p == n)
    total = len(pos_scores) * len(neg_scores)
    return (wins + ties) / total


def _pr_at_threshold(
    hack_scores: list[float],
    clean_scores: list[float],
    threshold: float,
) -> tuple[float, float, float]:
    """Precision, recall, FPR at a given NCC threshold (flag if NCC < threshold)."""
    tp = sum(1 for s in hack_scores if s < threshold)
    fn = sum(1 for s in hack_scores if s >= threshold)
    fp = sum(1 for s in clean_scores if s < threshold)
    tn = sum(1 for s in clean_scores if s >= threshold)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return round(precision, 3), round(recall, 3), round(fpr, 3)


def run_analysis(seed: int = 42) -> dict:
    """Full NCC separation analysis.

    Returns a result dict with calibration stats, AUC, held-out P/R/FPR,
    and complementarity data.
    """
    rng = random.Random(seed)

    # ── Load data ─────────────────────────────────────────────────────────────
    sorh = _load_sorh_python_samples()
    mbpp = _load_mbpp_samples()

    # ── 70/30 split on SORH ───────────────────────────────────────────────────
    rng.shuffle(sorh)
    split = max(1, int(0.7 * len(sorh)))
    sorh_cal = sorh[:split]
    sorh_held = sorh[split:]

    # ── Compute NCC for each estimator ────────────────────────────────────────
    def compute_all(samples: list[dict]) -> dict[str, list]:
        hack_z, ctrl_z, hack_c, ctrl_c, hack_l, ctrl_l = [], [], [], [], [], []
        skip = 0
        for s in samples:
            vz_h = ncc(s["hack"], s["tests"])
            vz_c = ncc(s["control"], s["tests"])
            vc_h = ncc_concat(s["hack"], s["tests"])
            vc_c = ncc_concat(s["control"], s["tests"])
            vl_h = ncc_lzma(s["hack"], s["tests"])
            vl_c = ncc_lzma(s["control"], s["tests"])
            if vz_h is None or vz_c is None:
                skip += 1
                continue
            hack_z.append(vz_h)
            ctrl_z.append(vz_c)
            if vc_h is not None and vc_c is not None:
                hack_c.append(vc_h)
                ctrl_c.append(vc_c)
            if vl_h is not None and vl_c is not None:
                hack_l.append(vl_h)
                ctrl_l.append(vl_c)
        return {
            "hack_z": hack_z, "ctrl_z": ctrl_z,
            "hack_c": hack_c, "ctrl_c": ctrl_c,
            "hack_l": hack_l, "ctrl_l": ctrl_l,
            "skip": skip,
        }

    cal_data = compute_all(sorh_cal)
    held_data = compute_all(sorh_held)

    # MBPP NCC (clean class, standalone — no paired control vs hack)
    mbpp_z, mbpp_skip = [], 0
    for s in mbpp:
        v = ncc(s["code"], s["tests"])
        if v is None:
            mbpp_skip += 1
        else:
            mbpp_z.append(v)

    # ΔNCC on calibration set
    delta_hacks, delta_ctrls = [], []
    sorh_tests = [s["tests"] for s in sorh_cal]
    for s in sorh_cal:
        # Foreign tests = randomly sampled from other samples
        candidates = [t for t in sorh_tests if t != s["tests"]]
        if not candidates:
            continue
        foreign = rng.choice(candidates)
        dh = delta_ncc(s["hack"], s["tests"], foreign)
        dc = delta_ncc(s["control"], s["tests"], foreign)
        if dh is not None:
            delta_hacks.append(dh)
        if dc is not None:
            delta_ctrls.append(dc)

    # ── Calibration: find threshold maximizing F1 on zdict NCC ───────────────
    thresholds = sorted(set(cal_data["hack_z"] + cal_data["ctrl_z"]))
    best_thresh, best_f1 = 0.0, 0.0
    for t in thresholds:
        p, r, _ = _pr_at_threshold(cal_data["hack_z"], cal_data["ctrl_z"], t)
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = t

    # ── Held-out evaluation ───────────────────────────────────────────────────
    held_p, held_r, held_fpr = _pr_at_threshold(
        held_data["hack_z"], held_data["ctrl_z"], best_thresh
    )

    # Complementarity: which hacks does NCC catch that ast-guard's dispatch misses?
    # (We can't run the full scan here without importing the core — just report
    #  the NCC results; complementarity analysis requires a separate runner pass.)

    return {
        "calibration": {
            "n_sorh_cal": len(sorh_cal),
            "n_sorh_held": len(sorh_held),
            "n_mbpp": len(mbpp),
            "sorh_skip": cal_data["skip"],
            "mbpp_skip": mbpp_skip,
            # zdict NCC distributions
            "hack_zdict": _describe(cal_data["hack_z"], "hack"),
            "ctrl_zdict": _describe(cal_data["ctrl_z"], "control"),
            "mbpp_zdict": _describe(mbpp_z, "mbpp-clean"),
            # concat NCC
            "hack_concat": _describe(cal_data["hack_c"], "hack"),
            "ctrl_concat": _describe(cal_data["ctrl_c"], "control"),
            # lzma NCC
            "hack_lzma": _describe(cal_data["hack_l"], "hack"),
            "ctrl_lzma": _describe(cal_data["ctrl_l"], "control"),
            # ΔNCC
            "delta_hack": _describe(delta_hacks, "hack"),
            "delta_ctrl": _describe(delta_ctrls, "control"),
            # AUC (hack=positive, ctrl=negative; lower NCC = hack)
            "auc_zdict": round(_auc(cal_data["hack_z"], cal_data["ctrl_z"]), 4),
            "auc_concat": round(_auc(cal_data["hack_c"], cal_data["ctrl_c"]), 4),
            "auc_lzma": round(_auc(cal_data["hack_l"], cal_data["ctrl_l"]), 4),
            "best_threshold": round(best_thresh, 4),
            "best_cal_f1": round(best_f1, 4),
        },
        "held_out": {
            "n": len(held_data["hack_z"]),
            "threshold": round(best_thresh, 4),
            "precision": held_p,
            "recall": held_r,
            "fpr": held_fpr,
            "hack_zdict": _describe(held_data["hack_z"], "hack"),
            "ctrl_zdict": _describe(held_data["ctrl_z"], "control"),
            "auc_zdict": round(_auc(held_data["hack_z"], held_data["ctrl_z"]), 4),
        },
    }


def print_report(result: dict) -> None:
    """Print a human-readable analysis report."""
    cal = result["calibration"]
    held = result["held_out"]

    print("=" * 65)
    print("NCC PROTOTYPE — SEPARATION ANALYSIS")
    print("=" * 65)
    print(f"\nDataset sizes:")
    print(f"  SORH calibration : {cal['n_sorh_cal']} samples  (skipped: {cal['sorh_skip']})")
    print(f"  SORH held-out    : {cal['n_sorh_held']} samples")
    print(f"  MBPP (clean)     : {cal['n_mbpp']} samples  (skipped: {cal['mbpp_skip']})")

    def row(stats: dict) -> str:
        return (
            f"  n={stats['n']:3d}  mean={stats['mean']:.3f}  "
            f"med={stats['median']:.3f}  "
            f"p25={stats['p25']:.3f}  p75={stats['p75']:.3f}  "
            f"[{stats['min']:.3f}–{stats['max']:.3f}]"
        )

    print(f"\n── NCC (zlib zdict) — calibration ──────────────────────────")
    print(f"  hack    {row(cal['hack_zdict'])}")
    print(f"  control {row(cal['ctrl_zdict'])}")
    print(f"  mbpp    {row(cal['mbpp_zdict'])}")
    print(f"  AUC (hack vs control): {cal['auc_zdict']}")

    print(f"\n── NCC (concat estimator) — calibration ─────────────────────")
    print(f"  hack    {row(cal['hack_concat'])}")
    print(f"  control {row(cal['ctrl_concat'])}")
    print(f"  AUC: {cal['auc_concat']}")

    print(f"\n── NCC (lzma) — calibration ─────────────────────────────────")
    print(f"  hack    {row(cal['hack_lzma'])}")
    print(f"  control {row(cal['ctrl_lzma'])}")
    print(f"  AUC: {cal['auc_lzma']}")

    print(f"\n── ΔNCC (own vs foreign tests) — calibration ────────────────")
    print(f"  hack    {row(cal['delta_hack'])}  (expect > 0)")
    print(f"  control {row(cal['delta_ctrl'])}  (expect ≈ 0)")

    print(f"\n── Calibration threshold ────────────────────────────────────")
    print(f"  Best NCC threshold : {cal['best_threshold']}")
    print(f"  Best calibration F1: {cal['best_cal_f1']:.3f}")

    print(f"\n── Held-out evaluation (NCC < {held['threshold']}) ──────────")
    print(f"  hack    {row(held['hack_zdict'])}")
    print(f"  control {row(held['ctrl_zdict'])}")
    print(f"  AUC    : {held['auc_zdict']}")
    print(f"  P={held['precision']:.3f}  R={held['recall']:.3f}  FPR={held['fpr']:.3f}")

    print(f"\n── Go/No-Go ─────────────────────────────────────────────────")
    auc = cal["auc_zdict"]
    held_r = held["recall"]
    held_fpr = held["fpr"]
    if auc >= 0.80 and held_r >= 0.60 and held_fpr <= 0.20:
        verdict = "GO — strong separation, proceed to Check integration"
    elif auc >= 0.65:
        verdict = "MARGINAL — signal present but threshold unstable; refine before integrating"
    else:
        verdict = "NO-GO — separation too weak; investigate root cause"
    print(f"  {verdict}")
    print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_analysis()
    print_report(result)
    # Persist result for further analysis
    out = Path(__file__).parent / "data" / "ncc_prototype_result.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"Full result written to {out}")
