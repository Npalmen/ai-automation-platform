"""Deterministic scenario generation for Kapitel 2G."""

from app.evaluation.generation.generator import GenerationResult, generate_batch
from app.evaluation.generation.manifest import build_generation_manifest
from app.evaluation.generation.provenance import GeneratedScenarioRecord, ScenarioProvenance

__all__ = [
    "GeneratedScenarioRecord",
    "GenerationResult",
    "ScenarioProvenance",
    "build_generation_manifest",
    "generate_batch",
]
