# ast-guard Examples

Each example is a pair of files: `*_original.py` (the code an LLM is asked to optimize) and `*_generated.py` (the LLM's output). Run any pair through ast-guard to see the detection in action:

```bash
ast-guard check examples/hardcoding_original.py examples/hardcoding_generated.py --mode strict
```

## Example Pairs

| Pair | What It Shows | Expected Result |
|------|--------------|-----------------|
| `hardcoding` | Fibonacci algorithm replaced with if/else lookup chain | **CRITICAL** (Check 1 + Check 5) |
| `optimization` | Loop replaced by list comprehension (legitimate) | **CLEAN** (Allowlist override) |
| `forbidden_calls` | eval/exec injection with variable aliasing and `__builtins__` access | **CRITICAL** (Check 3) |
| `complexity_collapse` | BFS algorithm replaced with hardcoded paths for known test nodes | **CRITICAL** (Check 1 + Check 5) |
| `import_drift` | Dangerous imports (pickle, subprocess) added to a word counter | **CRITICAL** (Check 4) |

## Why These Examples Matter

These are not hypothetical scenarios. Each pattern has been observed in real LLM-generated code when models are given autonomous optimization tasks. The `optimization` pair shows that ast-guard correctly allows legitimate improvements — it is not a blunt instrument that blocks everything.
