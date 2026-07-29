"""Network and external-write guards for automated regression tiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.evaluation.regression.constants import AUTOMATED_TIERS


class RegressionGuardError(RuntimeError):
    pass


@dataclass
class NetworkGuard:
    tier: str
    attempts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.tier not in AUTOMATED_TIERS:
            raise RegressionGuardError(f"network guard only applies to automated tiers, got {self.tier}")

    def record(self, host: str, *, call_site: str = "") -> None:
        redacted = f"{host}@{call_site}"[:120]
        self.attempts.append(redacted)
        raise RegressionGuardError(f"Forbidden network attempt: {redacted}")

    @property
    def count(self) -> int:
        return len(self.attempts)


@dataclass
class WriteBudgetGuard:
    tier: str
    budget: int = 0
    attempts: list[str] = field(default_factory=list)

    def record(self, provider: str, *, detail: str = "") -> None:
        self.attempts.append(f"{provider}:{detail}".strip(":"))
        raise RegressionGuardError(
            f"External write budget exceeded for tier {self.tier}: {provider}"
        )

    @property
    def count(self) -> int:
        return len(self.attempts)

    def assert_zero_budget(self, suite_budget: int) -> None:
        if suite_budget != 0:
            raise RegressionGuardError(f"Suite external_write_budget must be 0 for tier {self.tier}")


def install_regression_guards(
    network_guard: NetworkGuard,
    write_guard: WriteBudgetGuard,
) -> list[tuple[object, str, Callable]]:
    patches: list[tuple[object, str, Callable]] = []

    def _blocked_network(label: str) -> Callable:
        def _inner(*args, **kwargs):
            network_guard.record(label, call_site=label)

        return _inner

    def _blocked_write(label: str) -> Callable:
        def _inner(*args, **kwargs):
            write_guard.record(label)

        return _inner

    blocked_network = [
        ("app.evaluation.live.gmail_transport", "send_gmail_message", "gmail.send"),
        ("app.evaluation.live.gmail_transport", "poll_gmail_messages", "gmail.poll"),
        ("app.evaluation.live.llm_provider", "call_llm", "llm.call"),
        ("app.integrations.google.sheets_client", "append_row", "sheets.append"),
        ("app.integrations.monday.client", "create_item", "monday.create"),
        ("app.integrations.visma.client", "create_invoice", "visma.create"),
    ]
    blocked_writes = [
        ("app.evaluation.live.gmail_transport", "send_gmail_message", "gmail.send"),
        ("app.integrations.google.sheets_client", "append_row", "sheets.append"),
        ("app.integrations.monday.client", "create_item", "monday.create"),
        ("app.integrations.visma.client", "create_invoice", "visma.create"),
    ]
    import importlib

    for module_path, attr, label in blocked_network:
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, attr):
                patches.append((mod, attr, _blocked_network(label)))
        except ImportError:
            continue
    for module_path, attr, label in blocked_writes:
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, attr):
                patches.append((mod, attr, _blocked_write(label)))
        except ImportError:
            continue
    return patches
