"""No-network enforcement for 2G generation."""

from __future__ import annotations

import socket

import pytest

from app.evaluation.generation.generator import generate_batch


def test_no_network_socket_blocked(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked in 2G generation test")

    monkeypatch.setattr(socket, "socket", _blocked)
    result = generate_batch(templates_per_parent=2, base_seed=0)
    assert len(result.records) == 40


def test_generation_reports_zero_external_side_effects():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    for record in result.records:
        safety = record.scenario.expect.safety
        if isinstance(safety, dict):
            assert safety.get("real_external_calls", 0) == 0
        else:
            assert safety.real_external_calls == 0
