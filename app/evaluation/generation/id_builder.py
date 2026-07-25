"""Deterministic scenario and variation ID builders."""

from __future__ import annotations

import hashlib
import re


def _slug(value: str, *, max_len: int = 24) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return cleaned[:max_len].rstrip("_")


def build_variation_id(template_id: str, seed: int) -> str:
    return f"{template_id}__s{seed:04d}"


def build_scenario_id(parent_scenario_id: str, template_id: str, seed: int) -> str:
    parent_token = parent_scenario_id.split("_", 1)[0]
    template_token = _slug(template_id)
    digest = hashlib.sha256(f"{parent_scenario_id}|{template_id}|{seed}".encode("utf-8")).hexdigest()[:8]
    return f"2g_{parent_token}_{template_token}_s{seed:04d}_{digest}"
