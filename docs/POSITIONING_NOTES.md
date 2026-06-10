# Positioning Notes (README rewrite reference)

## (a) tree-sitter disclaimer

> The multilang adapters (Bash, JavaScript) use tree-sitter, a deterministic
> grammar-based parser — not an LLM — so they share no failure modes with the
> code generator being monitored.

## (b) Multilang v2.2.0 scope

The v2.2.0 multilang extension is deliberately "breadth, not depth": the
adapters expose the same check interface so that future pair-mode calibrations
developed for Python can be ported to Bash and JavaScript without structural
changes. They are scaffolding for that transfer, not an independent recall
claim.
