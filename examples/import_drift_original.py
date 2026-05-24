# examples/import_drift_original.py
# Original: Simple file content processor using only built-ins.

def count_words(text):
    """Count word frequencies in a text string."""
    words = text.lower().split()
    counts = {}
    for word in words:
        word = word.strip(".,!?;:")
        if word:
            counts[word] = counts.get(word, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
