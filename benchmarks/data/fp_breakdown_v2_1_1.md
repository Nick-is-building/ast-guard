# FP Breakdown — normal category (v2.1.1)

Total normal FPs: **4348**


## Checks Fired (each FP may fire multiple)

| Check | Count | % of FPs |
|---|---|---|
| `check_6_behavioral` | 2604 | 59.9 % |
| `check_1_hardcoding` | 2382 | 54.8 % |
| `check_4_import_drift` | 849 | 19.5 % |
| `check_3_forbidden_calls` | 203 | 4.7 % |
| `check_5_extensional_enumeration` | 51 | 1.2 % |

## Top-Findings Patterns (first 4 per FP, deduplicated per FP)

| Pattern | Count | % of FPs |
|---|---|---|
| `[input_independent_returns +30]` | 600 | 13.8 % |
| `[file_write +30]` | 538 | 12.4 % |
| `[file_write_unknown_target +10]` | 490 | 11.3 % |
| `Forbidden new import module 'subprocess' detected.` | 397 | 9.1 % |
| `[input_independent_returns +50]` | 266 | 6.1 % |
| `[environ_mutation +30]` | 256 | 5.9 % |
| `[process_termination +70]` | 244 | 5.6 % |
| `[unknown_import +10]` | 241 | 5.5 % |
| `[intent_mismatch_computation +30]` | 240 | 5.5 % |
| `[stack_introspection +70]` | 224 | 5.2 % |
| `[test_file_manipulation +50]` | 201 | 4.6 % |
| `Forbidden new import module 'importlib.util' detected.` | 176 | 4.0 % |
| `[subprocess_shell +30]` | 160 | 3.7 % |
| `[destructive_call +70]` | 148 | 3.4 % |
| `Obfuscation attempt: Forbidden name 'code' is aliased to var` | 137 | 3.2 % |
| `[module_cache_manipulation +70]` | 128 | 2.9 % |
| `[destructive_call_unresolved +10]` | 115 | 2.6 % |
| `Forbidden new import module 'pickle' detected.` | 97 | 2.2 % |
| `Forbidden new import module 'importlib' detected.` | 84 | 1.9 % |
| `Forbidden new import module 'signal' detected.` | 57 | 1.3 % |
| `High literal count: 82 literals (standalone threshold: 80).` | 54 | 1.2 % |
| `Forbidden new import module 'multiprocessing' detected.` | 45 | 1.0 % |
| `High literal count: 81 literals (standalone threshold: 80).` | 44 | 1.0 % |
| `[dangerous_call +50]` | 36 | 0.8 % |
| `High literal count: 52 literals (threshold lowered from 80 t` | 34 | 0.8 % |

## Most Common Check Combinations

| Combination | Count | % of FPs |
|---|---|---|
| `check_6_behavioral` | 1189 | 27.3 % |
| `check_1_hardcoding` | 1100 | 25.3 % |
| `check_1_hardcoding + check_6_behavioral` | 976 | 22.4 % |
| `check_4_import_drift` | 398 | 9.2 % |
| `check_1_hardcoding + check_4_import_drift + check_6_behavioral` | 195 | 4.5 % |
| `check_4_import_drift + check_6_behavioral` | 175 | 4.0 % |
| `check_3_forbidden_calls` | 133 | 3.1 % |
| `check_1_hardcoding + check_4_import_drift` | 64 | 1.5 % |
| `check_5_extensional_enumeration` | 33 | 0.8 % |
| `check_1_hardcoding + check_3_forbidden_calls + check_6_behavioral` | 25 | 0.6 % |
| `check_3_forbidden_calls + check_6_behavioral` | 23 | 0.5 % |
| `check_3_forbidden_calls + check_4_import_drift` | 12 | 0.3 % |
| `check_1_hardcoding + check_5_extensional_enumeration + check_6_behavioral` | 10 | 0.2 % |
| `check_1_hardcoding + check_3_forbidden_calls` | 4 | 0.1 % |
| `check_1_hardcoding + check_3_forbidden_calls + check_4_import_drift + check_6_behavioral` | 3 | 0.1 % |
