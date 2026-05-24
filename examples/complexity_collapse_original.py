# examples/complexity_collapse_original.py
# Original: BFS shortest path with proper graph traversal.

from collections import deque

def shortest_path(graph, start, end):
    """Find shortest path in unweighted graph using BFS."""
    if start == end:
        return [start]
    visited = set()
    queue = deque([(start, [start])])
    while queue:
        node, path = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, []):
            new_path = path + [neighbor]
            if neighbor == end:
                return new_path
            if neighbor not in visited:
                queue.append((neighbor, new_path))
    return []
