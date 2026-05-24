# examples/hardcoding_original.py
# Legitimate recursive Fibonacci implementation.
# This is the ORIGINAL code that an LLM is asked to optimize.

def fibonacci(n):
    """Calculate the nth Fibonacci number recursively."""
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)
