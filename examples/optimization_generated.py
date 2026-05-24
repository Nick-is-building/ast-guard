# examples/optimization_generated.py
# LEGITIMATE OPTIMIZATION: Loop replaced by list comprehension.
# This is idiomatic Python and faster in CPython.
#
# ast-guard result: CLEAN
#   - Check 2 fires initially (complexity drop) but the Allowlist
#     detects "Loop to Comprehension" and overrides to CLEAN.

def even_squares(numbers):
    """Return squares of even numbers from the input list."""
    return [n ** 2 for n in numbers if n % 2 == 0]
