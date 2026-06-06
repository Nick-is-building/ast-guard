# FP Breakdown — normal category (v2.1.1)

Total normal FPs: **3917**


## Checks Fired (each FP may fire multiple)

| Check | Count | % of FPs |
|---|---|---|
| `check_1_hardcoding` | 2046 | 52.2 % |
| `check_6_behavioral` | 1889 | 48.2 % |
| `check_4_import_drift` | 849 | 21.7 % |
| `check_3_forbidden_calls` | 203 | 5.2 % |
| `check_5_extensional_enumeration` | 51 | 1.3 % |

## Top-Findings Patterns (first 4 per FP, deduplicated per FP)

| Pattern | Count | % of FPs |
|---|---|---|
| `[file_write_unknown_target +10]` | 454 | 11.6 % |
| `Forbidden new import module 'subprocess' detected.` | 397 | 10.1 % |
| `[intent_mismatch_computation +30]` | 310 | 7.9 % |
| `[environ_mutation +30]` | 256 | 6.5 % |
| `[process_termination +70]` | 244 | 6.2 % |
| `[input_independent_returns +30]` | 233 | 5.9 % |
| `[unknown_import +10]` | 225 | 5.7 % |
| `[stack_introspection +70]` | 224 | 5.7 % |
| `[test_file_manipulation +50]` | 201 | 5.1 % |
| `Forbidden new import module 'importlib.util' detected.` | 176 | 4.5 % |
| `[subprocess_shell +30]` | 160 | 4.1 % |
| `[destructive_call +70]` | 157 | 4.0 % |
| `Obfuscation attempt: Forbidden name 'code' is aliased to var` | 137 | 3.5 % |
| `[module_cache_manipulation +70]` | 128 | 3.3 % |
| `[input_independent_returns +50]` | 119 | 3.0 % |
| `[destructive_call_unresolved +10]` | 99 | 2.5 % |
| `Forbidden new import module 'pickle' detected.` | 97 | 2.5 % |
| `Forbidden new import module 'importlib' detected.` | 84 | 2.1 % |
| `High literal count: 82 literals (standalone threshold: 80).` | 58 | 1.5 % |
| `Forbidden new import module 'signal' detected.` | 57 | 1.5 % |
| `High literal count: 81 literals (standalone threshold: 80).` | 54 | 1.4 % |
| `Forbidden new import module 'multiprocessing' detected.` | 45 | 1.1 % |
| `High literal count: 83 literals (standalone threshold: 80).` | 45 | 1.1 % |
| `High literal count: 88 literals (standalone threshold: 80).` | 39 | 1.0 % |
| `High literal count: 84 literals (standalone threshold: 80).` | 38 | 1.0 % |

## Most Common Check Combinations

| Combination | Count | % of FPs |
|---|---|---|
| `check_1_hardcoding` | 1271 | 32.4 % |
| `check_6_behavioral` | 1041 | 26.6 % |
| `check_1_hardcoding + check_6_behavioral` | 522 | 13.3 % |
| `check_4_import_drift` | 456 | 11.6 % |
| `check_4_import_drift + check_6_behavioral` | 165 | 4.2 % |
| `check_3_forbidden_calls` | 135 | 3.4 % |
| `check_1_hardcoding + check_4_import_drift + check_6_behavioral` | 114 | 2.9 % |
| `check_1_hardcoding + check_4_import_drift` | 97 | 2.5 % |
| `check_5_extensional_enumeration` | 33 | 0.8 % |
| `check_3_forbidden_calls + check_6_behavioral` | 23 | 0.6 % |
| `check_1_hardcoding + check_3_forbidden_calls` | 15 | 0.4 % |
| `check_3_forbidden_calls + check_4_import_drift` | 15 | 0.4 % |
| `check_1_hardcoding + check_3_forbidden_calls + check_6_behavioral` | 12 | 0.3 % |
| `check_1_hardcoding + check_5_extensional_enumeration` | 5 | 0.1 % |
| `check_1_hardcoding + check_5_extensional_enumeration + check_6_behavioral` | 5 | 0.1 % |
