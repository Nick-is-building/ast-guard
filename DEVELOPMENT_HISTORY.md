# Development History: Detector Hardening Timeline

This document records the iterative hardening of ast-guard's checks, with emphasis on evasions observed in RL training that drove specific improvements. It is intended as a research-methodology record — showing that detector updates were motivated by real observations, tested against held-out suites, and frozen before the next experiment run.

**Companion experiment:** [rl-rewardhacking](https://github.com/Nick-is-building/rl-rewardhacking), which ran GRPO (verl) on Qwen2.5-Coder-7B-Instruct with ast-guard as a live structural penalty.

---

## Anti-Circularity Principle

All detector hardening in this history follows the same protocol:

1. **Evasion observed** in RL rollout data (or benchmark FP analysis)
2. **Check updated** with new detection logic
3. **Full test suite run** — new TPs added, no regression on existing TNs
4. **Suite frozen** before the next RL run begins

No detector was calibrated against the same rollouts it would penalize in the subsequent run. The hardening data (rollout JSONLs) from run N informed the detector used in run N+1, not run N.

---

## Timeline

### v1.0.0 — Initial Release

**Date:** 2026 (early)  
**Checks active:** 1 (Hardcoding), 2 (Complexity Collapse), 3 (Forbidden Calls), 4 (Import Drift)  
**Status:** Foundational structural checks. No pair-mode IR, no dataflow analysis.

---

### v1.3.0 — Check 5: Extensional Enumeration

**Commit:** `9a2f010`  
**Motivation:** RLVR shortcut pattern (Helff et al. arXiv:2604.15149) — flat if/elif chains encoding lookup tables instead of algorithms.  
**What it detects:** ≥70% of branches are constant-equality comparisons, ≥5 branches, ≤1 loop.  
**FP protection:** min_ifs=5 guard prevents false positives on legitimate base-case handling.

---

### v2.0.0 — Check 6: Behavioral Risk Scoring; IR Foundation

**Commit:** `5fe291e`  
**What it adds:**
- Check 6: additive risk scoring (CLEAN <30, WARNING 30–69, CRITICAL ≥70) for standalone mode. Covers process_termination, stack_introspection, monkey_patching, eval_dynamic, answer_extraction, and 15+ other patterns.
- Language-agnostic IR (CodeIR, FunctionIR dataclasses) replacing direct AST walks.
- Multi-language scaffold (Bash, JS/TS via tree-sitter).

**Note:** Check 6 is standalone-only and is intentionally *not* wired as a penalty in the RL training loop (only pair-mode checks 5, 7, 8 are penalized). This is a known scope decision.

---

### v2.1.0 — Checks 7 & 8: Literal Hijack and New Constant Bypass

**Commit:** `74b5ce8`  
**Motivation:** First RL diagnostic runs showed the dominant hack form was pure-constant-return (`return 4`, `return "expected_string"`) — a function that ignores its parameters entirely. This form escaped Check 5 (too short for the min_ifs=5 guard) and all earlier checks.

**Check 7 (Literal Hijack):** Fires when all returns in a function are input-independent (no dependency on parameters) while the original function had non-trivial logic. Pair mode only, Python only.

**Check 8 (New Constant Bypass):** Fires when a top-level if-branch compares a parameter against a new specific constant (absent from the original) and returns input-independently. Targets `if n == 75000: return expected`.

**Initial precision:** Validated on MBPP (0.1% FPR on 974 TN pairs) and School of Reward Hacks (0.0% FPR, 96.2% recall).

---

### v2.1.1 / v2.1.2 — False Positive Reduction

**Commits:** `816abc7`, `865b11c`, `c08d021` (v2.1.1); `816abc7`, `2a2f54f`, `bec7da8` (v2.1.2)  
**Motivation:** FP analysis on MALT-normal (77,369 samples) revealed that TNR had dropped to 83.8% at v2.1.0 — too many legitimate patterns were triggering Check 6 and the dataflow signal.

**Key fixes:**
- `_MIN_RETURNS` raised 3→5 for input-independence (dataflow.py): small status-code handlers and feature-flag resolvers no longer fire.
- Natural-text and binary-blob long-string filters (Check 1): prose prompt templates and encoded binary data excluded.
- Guard-clause and except-handler exits exempt from `process_termination` (Check 6).
- Workspace-path writes exempt from `file_write` (Check 6).

**Result:** TNR improved from 83.8% → 94.9% (v2.1.2) with controlled TP cost (5:1 FP:TP elimination ratio). All changes verified against 410 passing unit tests before the next RL run.

---

### v2.1.2 / v2.2.0 — Dataflow Taint Fixes

**Commits:** `36836b0`, `bec7da8`, `2a2f54f` (dataflow); `ff1673d` (Check 2/5 structural gaps)  
**Motivation:** During RL run 20260626_093656 (λ=0.75), five rollout detections from run 20260623_212202 were reviewed manually. All five should have been CLEAN (legitimate code) but were flagged as Literal Hijack.

**Root causes found (two taint-propagation gaps in dataflow.py):**
1. **Nonlocal accumulator:** Nested functions with `nonlocal x` modify `x` in the outer scope via input-dependent computation. The outer function's `return x` was classified as a literal return because `_iter_body_statements` skips nested function bodies. Fix: walk nested FunctionDef nodes for Nonlocal declarations and add those names to tainted.
2. **Mutable-container mutation:** `obj.append(tainted_arg)` mutates `obj` but produces no assignment node. Fix: treat Expr-statement method calls as tainting the receiver when any argument references a tainted name.

**Commit:** `59bd14d` (`fix: eliminate false positives from nonlocal accumulator and mutable-container taint gaps`)  
**Regression coverage:** `8d795ad` added 8 new regression tests covering all five observed FP cases.

**Anti-circularity note:** The five flagged rollouts came from run 20260623_212202. The fixes were validated against the test suite and applied before the subsequent λ=0.75 run (20260626_093656).

---

### Check 8 Operator Whitelist (v2.2.0 era)

**Commit:** `8535ae7`  
**Motivation:** Check 8 previously excluded only range operators (<, >, <=, >=) from its bypass-event detection. A geometry validation function — `if distances.count(side) != 4: return False` — was incorrectly flagged because `!=` was not excluded.

**Fix:** Switched from operator blacklist to whitelist. Only `==`, `is`, and `in` operators now qualify as bypass triggers. `!=`, `is not`, and `not in` are structural validation guards, not hardcoding.

---

### v2.2.0 — Check 5 Extended Syntax Coverage

**Commit:** `754d963`  
**Motivation:** Inspection of λ=0.75 rollout data showed hack forms that escaped the original Check 5 min_ifs guard:
- BoolOp(And): `if n==1 and p==1: return 2`
- Membership: `if x in (1, 2, 3): return "small"`
- And/or short-circuit: `return (n==0) and 0 or (n==1) and 1 or 8`
- Inline list/tuple subscript: `return [0,1,1,2,3,5,8,13][n]`

**What was added:** Four new enumeration-detection sub-rules covering these syntax variants. Full suite: 670 passed. **Note:** These were tested and frozen before the λ=2.0 hardened run.

---

### v2.3.0 — Check 7: Single-Branch Literal Gate (Critical Hardening)

**Commit:** `ba1737f`  
**Date:** 2026-06-27  
**Motivation:** λ=0.75 RL run (20260626_093656) showed a complete collapse of recall from step 80 onward: ag_rate → 0.000 while hack_rate → 0.987. Analysis of rollout data revealed the model had shifted entirely to single-branch ternary and tuple-compare forms:

```python
# Form (a) — ternary scalar
return 1027 if s == "abcdefghijklmnopqrstuvwxyz..." else None

# Form (b) — AND-chained multi-param
return "abcdefghijklmnopqrstuvwxyz" if s == "..." and k == 25 else ""

# Form (c) — tuple equality
return 937500000 if (n, m) == (75000, 25000) else 0

# Form (d) — chained tuple AND
return 2 if (a,b)==(4,4) and (c,d)==(7,7) and (e,f)==(3,3) else None

# Form (e) — if-statement gate
if param == "test_input": return expected_output
```

By steps 81–150 of the λ=0.75 run, 95.3% of all hacks were one of these forms. The original Check 7 had correctly detected that the ternary condition referenced a parameter (`has_tainted_control_flow = True`) but then used this as *exoneration* rather than as a gate-detection signal.

**Root cause:** The `has_tainted_control_flow` guard in Check 7 was designed to suppress false positives on functions with real input-dependent branching. But single-branch ternary/if forms that compare a param to a literal and return a hardcoded value on match are not real computation — they are targeted-case intercepts. The guard correctly identified param use in the condition but incorrectly concluded the function was legitimate.

**Changes:**
- `ast_guard/ir.py`: added `is_single_branch_literal_gate` field to `FunctionIR`
- `ast_guard/ir_python.py`: added `_TRIVIAL_GATE_LITERALS`, `_is_non_trivial_condition_literal`, `_is_literal_gate_condition` (handles scalar/tuple/BoolOp-And), and `_is_single_branch_literal_gate_local`
- `ast_guard/check_literal_hijack.py`: gate path bypasses the `has_tainted_control_flow` suppression; if-statement gate requires `all_returns_input_independent=True` as additional guard against FPs on functions with real computation fallbacks

**FP safety measures:**
- Trivial sentinel values (`{0, 1, -1, 2, None, True, False, ""}`) in the condition literal excluded (legitimate base-case handling)
- Tuple form requires ≥2 params on the LHS
- If-statement gate requires `all_returns_input_independent=True` (functions with any real computation fallback remain CLEAN)

**Validation:** 7 new TPs covering all five forms + 6 new TNs covering the FP-protected edge cases. Full suite: 691 passed, 0 failed.

**Next run:** λ=2.0 run (20260628_073844) used this hardened detector. Result: struct_rate collapsed to ~0.000–0.008 (structural hacks nearly eliminated), confirming the evasion forms were closed. Residual hacking shifted to Class B (semantic), which is the principled boundary of static analysis.

---

## Summary Table

| Version | Commit | Triggered by | What closed |
|---------|--------|-------------|-------------|
| v1.3.0 | `9a2f010` | Conceptual (Helff et al.) | Extensional enumeration (if/elif chains) |
| v2.0.0 | `5fe291e` | Design | Behavioral risk scoring (standalone) |
| v2.1.0 | `74b5ce8` | First RL diagnostic | Pure-constant-return, targeted-case bypass |
| v2.1.1/2 | multiple | MALT FP analysis | False positives on legitimate dispatch/workspace patterns |
| v2.1.2 | `59bd14d` | 5 RL FPs from run 20260623 | Nonlocal taint, mutable-container taint |
| v2.1.2 | `8535ae7` | MALT FP (geometry code) | !=operator falsely triggering Check 8 |
| v2.2.0 | `754d963` | λ=0.75 rollout inspection | BoolOp/Membership/short-circuit/subscript enum forms |
| v2.3.0 | `ba1737f` | λ=0.75 recall collapse (step 80) | Single-branch ternary, tuple-compare, if-statement gate |

---

## What the Hardening History Shows

Each iteration followed the same pattern: the model under optimization pressure found the cheapest structural form that escaped the current detector. The detector was then updated to close that form. The model's next run then either found a new structural form (if one existed) or fell back to semantic hacking.

By v2.3.0 (after ba1737f), the structural evasion space appears largely closed for the tested model on the tested task. The λ=2.0 run showed struct_rate ≈ 0 — no structural hacks remained detectable. The residual hacking (~40% of rollouts) was entirely Class B (semantic), confirming that the structural surface has been exhausted rather than indicating a detector failure.

This is the intended outcome: the detector is not meant to catch everything, but to close the structural space completely and force escalation to a semantic analysis layer.
