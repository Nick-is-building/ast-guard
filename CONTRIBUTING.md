# Contributing to ast-guard

Thanks for your interest in contributing. ast-guard is a small, focused project and contributions are welcome.

## Getting Started

```bash
git clone https://github.com/Nick-is-building/ast-guard.git
cd ast-guard
python -m pytest tests/ -v
```

No dependencies to install. Python 3.11+ is required.

## What We Need Help With

- **New obfuscation bypass patterns**: If you find a way an LLM can evade detection, open an issue with a code sample. This is the highest-value contribution.
- **Benchmark samples**: Additional hacked or benign code pairs for the `benchmarks/` suite.
- **Threshold calibration data**: Run ast-guard in audit mode on your projects and export anonymized telemetry.
- **Integration examples**: Using ast-guard with other agent frameworks, CI/CD pipelines, or MCP clients.

## How to Contribute

1. Fork the repository.
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes.
4. Run the full test suite: `python -m pytest tests/ -v`
5. Open a pull request with a clear description of what changed and why.

## Code Style

- No external dependencies in the core package (only Python standard library).
- Every check must have corresponding test cases for both true positives and true negatives.
- Docstrings on all public functions.
- Comments should explain *why*, not *what*.

## Reporting Bypass Vulnerabilities

If you find a way to bypass ast-guard's detection (e.g., an obfuscation pattern that slips through Check 3), please open a GitHub issue. These are not security vulnerabilities in the traditional sense — they are detection gaps that improve the tool. Public disclosure is encouraged.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
