"""Safety guards for customer-domain stateful evaluation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from app.tools.test_environment.guards import GuardError, is_env_allowed, verify_database_fingerprint

EVAL_TENANT_PREFIX = "eval_cd_"
REQUIRED_DB_NAME_FRAGMENT = "customer_domain_eval"


class EvalGuardError(RuntimeError):
    pass


@dataclass
class ExternalSideEffectGuard:
    """Fail-fast registry for forbidden external adapter usage."""

    violations: list[str] = field(default_factory=list)

    def record(self, adapter: str, detail: str = "") -> None:
        message = f"{adapter}:{detail}".strip(":")
        self.violations.append(message)
        raise EvalGuardError(f"Forbidden external side effect: {message}")

    @property
    def count(self) -> int:
        return len(self.violations)


def assert_eval_environment() -> None:
    if not is_env_allowed():
        env = os.environ.get("ENV", "")
        raise EvalGuardError(f"ENV '{env}' is not allowlisted for customer-domain evaluation.")


def assert_eval_database_url(database_url: str) -> str:
    if not database_url.strip():
        raise EvalGuardError("DATABASE_URL is required for customer-domain evaluation.")
    dialect = database_url.split(":", 1)[0].lower()
    if dialect not in {"postgresql", "postgres"}:
        raise EvalGuardError("Customer-domain stateful evaluation requires PostgreSQL.")
    allowed, reason = verify_database_fingerprint(database_url)
    if not allowed:
        raise EvalGuardError(f"DATABASE_URL failed fingerprint check: {reason}")
    db_name = database_url.rsplit("/", 1)[-1].lower()
    if REQUIRED_DB_NAME_FRAGMENT not in db_name:
        raise EvalGuardError(
            f"Database name must contain '{REQUIRED_DB_NAME_FRAGMENT}' "
            f"(got '{db_name}')."
        )
    return db_name


def install_external_guards(guard: ExternalSideEffectGuard) -> list[tuple[object, str, Callable]]:
    """Return patch tuples for unittest.mock.patch context stacking."""
    patches: list[tuple[object, str, Callable]] = []

    def _blocked(name: str) -> Callable:
        def _inner(*args, **kwargs):
            guard.record(name)

        return _inner

    blocked_modules = [
        ("app.evaluation.live.gmail_transport", "send_gmail_message", "gmail.send"),
        ("app.evaluation.live.gmail_transport", "poll_gmail_messages", "gmail.poll"),
        ("app.evaluation.live.llm_provider", "call_llm", "llm.call"),
        ("app.evaluation.live.eval_llm_client", "complete", "llm.complete"),
    ]
    for module_path, attr, label in blocked_modules:
        try:
            import importlib

            mod = importlib.import_module(module_path)
            if hasattr(mod, attr):
                patches.append((mod, attr, _blocked(label)))
        except ImportError:
            continue
    return patches
