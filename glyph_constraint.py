from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "v1"
LOWER_THRESHOLD = 0.33
UPPER_THRESHOLD = 0.50
REFERENCE_POINT = 0.39

SUBORDINATED = "SUBORDINATED"
STRUCTURAL = "STRUCTURAL"
DOMINANT = "DOMINANT"


@dataclass(frozen=True)
class Partitions:
    x: float
    y: float


def compute_structural_constraint_ratio(parts: Partitions) -> float:
    denom = parts.x + (parts.y ** 2)
    if denom <= 0:
        raise ValueError("x + y^2 must be greater than zero")
    ratio = parts.x / denom
    if ratio < 0:
        raise ValueError("ratio cannot be negative")
    return ratio


def classify_zone(ratio: float) -> str:
    if ratio < LOWER_THRESHOLD:
        return SUBORDINATED
    if ratio <= UPPER_THRESHOLD:
        return STRUCTURAL
    return DOMINANT
