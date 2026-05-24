# examples/forbidden_calls_original.py
# Original code: simple string processing, no system access.

def process_data(items):
    """Process a list of items and return formatted strings."""
    results = []
    for item in items:
        cleaned = item.strip().lower()
        if cleaned:
            results.append(f"processed: {cleaned}")
    return results
