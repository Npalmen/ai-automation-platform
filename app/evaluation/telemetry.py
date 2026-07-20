"""Execution telemetry for evaluation runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import local

_state = local()


@dataclass
class ExecutionTelemetry:
    execution_function_calls: int = 0
    fake_adapter_calls: int = 0
    real_external_calls: int = 0
    calls_by_action_type: dict[str, int] = field(default_factory=dict)

    def reset(self) -> None:
        self.execution_function_calls = 0
        self.fake_adapter_calls = 0
        self.real_external_calls = 0
        self.calls_by_action_type.clear()

    def record_fake_adapter(self, action: str) -> None:
        self.fake_adapter_calls += 1
        self.calls_by_action_type[action] = self.calls_by_action_type.get(action, 0) + 1

    def record_real_external(self) -> None:
        self.real_external_calls += 1

    def record_execution_call(self) -> None:
        self.execution_function_calls += 1

    def as_dict(self) -> dict:
        return {
            "execution_function_calls": self.execution_function_calls,
            "fake_adapter_calls": self.fake_adapter_calls,
            "real_external_calls": self.real_external_calls,
            "calls_by_action_type": dict(self.calls_by_action_type),
        }


def get_telemetry() -> ExecutionTelemetry:
    tel = getattr(_state, "telemetry", None)
    if tel is None:
        tel = ExecutionTelemetry()
        _state.telemetry = tel
    return tel


def reset_telemetry() -> ExecutionTelemetry:
    tel = get_telemetry()
    tel.reset()
    return tel
