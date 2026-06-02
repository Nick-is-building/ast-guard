# Security Policy

## Scope

ast-guard is a **detection tool**, not a sandbox. It analyzes code structure before execution but does not execute or isolate code. It is designed to be one layer in a defense-in-depth strategy.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | ✅         |
| 1.3.x   | ⚠️ Upgrade recommended |
| < 1.3   | ❌         |

## Reporting Detection Bypasses

If you discover an obfuscation pattern or code structure that evades ast-guard's checks, please **open a public GitHub issue**. Detection bypasses are not treated as confidential security vulnerabilities — they are detection gaps that benefit the entire community when disclosed openly.

Include:
- A minimal Python code pair (original + generated) that demonstrates the bypass.
- Which check(s) you expected to fire.
- Your Python version.

## Reporting Security Vulnerabilities

For actual security issues in ast-guard's own code (e.g., a path traversal in the telemetry system, or a way to execute arbitrary code through the CLI), please email the maintainer directly rather than opening a public issue.

Contact: Open a private GitHub security advisory via the [Security tab](https://github.com/Nick-is-building/ast-guard/security).

## Design Principles

- **No code execution**: ast-guard never executes the code it analyzes.
- **No network calls**: The scan path makes zero network requests.
- **No external dependencies**: The core package uses only the Python standard library, minimizing supply chain risk.
- **Privacy by design**: Telemetry stores only anonymized metrics. No code, filenames, paths, or timestamps are ever recorded.
