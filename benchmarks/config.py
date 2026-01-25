"""Configuration models and loader for the benchmark framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class Coordinate:
    """A geographic coordinate."""

    lat: float
    lng: float


@dataclass
class TestCase:
    """A single benchmark test case."""

    name: str
    category: str  # "small_town" | "large_city" | "cross_shard"
    start: Coordinate
    end: Coordinate
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> TestCase:
        """Create a TestCase from a dictionary."""
        return cls(
            name=data["name"],
            category=data["category"],
            start=Coordinate(lat=data["start"]["lat"], lng=data["start"]["lng"]),
            end=Coordinate(lat=data["end"]["lat"], lng=data["end"]["lng"]),
            description=data.get("description", ""),
        )


@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark run."""

    test_cases: List[TestCase] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> BenchmarkConfig:
        """Load configuration from a YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        test_cases = [TestCase.from_dict(tc) for tc in data.get("test_cases", [])]
        return cls(test_cases=test_cases)

    def filter_by_category(self, category: str) -> List[TestCase]:
        """Get test cases filtered by category."""
        return [tc for tc in self.test_cases if tc.category == category]

    @property
    def categories(self) -> List[str]:
        """Get unique categories in the config."""
        return list(set(tc.category for tc in self.test_cases))
