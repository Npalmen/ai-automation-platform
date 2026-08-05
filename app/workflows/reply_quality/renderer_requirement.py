"""Renderer requirement modes for coworker replies."""

from __future__ import annotations

from enum import Enum


class RendererRequirement(str, Enum):
    DEFAULT = "default"
    CONSTRAINED_LLM_REQUIRED = "constrained_llm_required"
