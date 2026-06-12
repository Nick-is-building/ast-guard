"""
Benchmark Ingestion Framework for ast-guard (Phase 3).

Provides a unified interface for loading reward-hacking benchmark datasets
from multiple sources, all producing CodePair records for the benchmark runner.
"""
from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class CodePair(TypedDict):
    original_code: str
    generated_code: str
    language: str
    benchmark: str
    category: str
    sample_id: str
    metadata: dict


_REQUIRED_FIELDS = frozenset(CodePair.__annotations__)


def validate_code_pair(pair: dict) -> bool:
    """Return True if dict has all required CodePair fields with correct types."""
    if not isinstance(pair, dict):
        return False
    if not _REQUIRED_FIELDS.issubset(pair):
        return False
    for field in ("original_code", "generated_code", "language", "benchmark",
                  "category", "sample_id"):
        if not isinstance(pair.get(field), str):
            return False
    if not isinstance(pair.get("metadata"), dict):
        return False
    return True


class BenchmarkLoader(ABC):
    """Base class for benchmark dataset loaders."""

    name: str  # subclasses must set this class attribute

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or (
            Path.home() / ".ast-guard" / "benchmarks" / self.name
        )

    @abstractmethod
    def download(self) -> None:
        """Download or clone the dataset to self.data_dir."""

    @abstractmethod
    def load_samples(self) -> list[CodePair]:
        """Load all samples and return them as CodePair records."""

    def is_available(self) -> bool:
        """Return True if the dataset has already been downloaded."""
        return self.data_dir.exists() and any(self.data_dir.iterdir())


_REGISTRY: dict[str, type[BenchmarkLoader]] = {}


def register(cls: type[BenchmarkLoader]) -> type[BenchmarkLoader]:
    """Class decorator that registers a loader in the global registry."""
    _REGISTRY[cls.name] = cls
    return cls


def get_loader(name: str) -> BenchmarkLoader:
    """Return an instance of the named loader; raises KeyError if unknown."""
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown benchmark {name!r}. Available: {available}")
    return _REGISTRY[name]()


def get_all_loaders() -> list[BenchmarkLoader]:
    """Return instances of all registered loaders."""
    return [cls() for cls in _REGISTRY.values()]


# Import loaders to trigger registration (must come after registry is defined).
from .terminal_wrench import TerminalWrenchLoader  # noqa: E402, F401
from .evilgenie import EvilGenieLoader  # noqa: E402, F401
from .trace_loader import TraceLoader  # noqa: E402, F401
from .countdown_code import CountdownCodeLoader  # noqa: E402, F401
from .school_of_hacks import SchoolOfHacksLoader  # noqa: E402, F401
from .specbench import SpecBenchLoader  # noqa: E402, F401
from .malt_loader import MaltLoader  # noqa: E402, F401
from .mbpp import MbppLoader  # noqa: E402, F401
from .humaneval import HumanEvalLoader  # noqa: E402, F401
from .apps import AppsLoader  # noqa: E402, F401
from .generator_loader import GeneratorLoader  # noqa: E402, F401
