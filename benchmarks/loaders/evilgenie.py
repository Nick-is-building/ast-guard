"""
Stub loader for EvilGenie.

EvilGenie (github.com/JonathanGabor/EvilGenie) is a live execution harness:
agents run inside a sandboxed environment and compete against a running judge.
There is no released static dump of (original_code, hacked_code) pairs.
load_samples() always returns [].

To use EvilGenie data, generate agent rollouts using the harness and export
them as (original, generated, label) JSON, then write a custom loader.

Reference: LiveCodeBench-based problems, 154 hard problems (v5/v6).
"""
from __future__ import annotations

import logging
from pathlib import Path

from benchmarks.loaders import BenchmarkLoader, CodePair, register

logger = logging.getLogger(__name__)


@register
class EvilGenieLoader(BenchmarkLoader):
    """Stub — EvilGenie has no static pair dataset; always returns empty."""

    name = "evilgenie"

    def download(self) -> None:
        logger.info("EvilGenie is a live harness; nothing to download.")

    def is_available(self) -> bool:
        return False

    def load_samples(self) -> list[CodePair]:
        logger.info("EvilGenie: no static pairs available (live harness only).")
        return []
