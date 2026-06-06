# ast-guard MALT Validation Run — post commit ff1673d

Validation run after structural fix commit `ff1673d` (four detection gap closures in
Check 2 and Check 5). Numbers are identical to v2.2.0 — confirming the fixes introduce
no MALT regression. Expected: fixes affect pair-mode correctness only (Check 2 partial
rename / dropped function) or standalone edge cases with zero net MALT impact
(match_case wildcard filter, Bash single-bracket `[ ]` enumeration).

| Benchmark | Samples | Detected | Detection Rate | Skipped |
|-----------|---------|----------|---------------|---------|
| malt | 81515 | 4944 | 6.1% | 0 |

| Label | Total | Detected | Detection Rate |
|-------|-------|----------|---------------|
| normal | 77,369 | 3,888 | 5.0% (FPR) |
| bypass_constraints | 2,379 | 820 | 34.5% |
| hardcoded_solution | 429 | 201 | 46.9% |
| sabotage | 197 | 15 | 7.6% |
