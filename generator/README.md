# generator

Produces synthetic reward-hack samples for augmenting ast-guard benchmarks.
Starting from seed problems, it applies parameterised hack strategies (one per
TRACE category), verifies each candidate against visible and hidden tests, and
emits labelled (original, generated, expected_verdict) triples.
