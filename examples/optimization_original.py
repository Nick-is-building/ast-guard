# examples/optimization_original.py
# Original code with explicit loop for filtering even squares.

def even_squares(numbers):
    """Return squares of even numbers from the input list."""
    result = []
    for n in numbers:
        if n % 2 == 0:
            result.append(n ** 2)
    return result
