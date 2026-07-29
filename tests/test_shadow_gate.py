"""Shadow gate fail-closed tests."""

from __future__ import annotations

import pytest

from app.services.shadow_gate import ShadowGateError, assert_shadow_intake_allowed


def test_shadow_intake_disabled_by_default():
    with pytest.raises(ShadowGateError) as exc:
        assert_shadow_intake_allowed("T_EVAL")
    assert exc.value.code == "SHADOW_INTAKE_DISABLED"
