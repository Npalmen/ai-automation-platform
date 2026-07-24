"""Environment configuration for live evaluation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from app.core.settings import Settings, get_settings


@dataclass(frozen=True)
class LiveEvalConfig:
    enabled: bool
    gmail_enabled: bool
    llm_enabled: bool
    seed_allowed: bool
    purge_allowed: bool
    tenant_ids: frozenset[str]
    sender_emails: frozenset[str]
    recipient_emails: frozenset[str]
    reply_domains: frozenset[str]
    intake_label: str
    max_scenarios_per_run: int
    max_gmail_sends_per_run: int
    max_gmail_replies_per_run: int
    max_llm_calls_per_run: int
    max_runtime_minutes: int
    storage_root: str
    env_fingerprint: str
    external_side_effects_enabled: bool
    sender_eval_label: str
    llm_provider: str
    llm_model: str
    llm_timeout: float
    llm_max_tokens: int


def _parse_csv_set(raw: str) -> frozenset[str]:
    return frozenset(item.strip() for item in (raw or "").split(",") if item.strip())


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


@lru_cache
def get_live_eval_config(settings: Settings | None = None) -> LiveEvalConfig:
    settings = settings or get_settings()
    storage_root = os.path.join(settings.STORAGE_PATH, "live_eval")
    db_url = settings.DATABASE_URL or ""
    fingerprint = f"{settings.ENV}@{db_url.rsplit('/', 1)[-1]}"
    return LiveEvalConfig(
        enabled=_env_truthy("LIVE_EVAL_ALLOWED") and settings.ENV == "test",
        gmail_enabled=_env_truthy("LIVE_GMAIL_EVAL_ALLOWED"),
        llm_enabled=_env_truthy("LIVE_LLM_EVAL_ALLOWED"),
        seed_allowed=_env_truthy("LIVE_EVAL_SEED_ALLOWED"),
        purge_allowed=_env_truthy("LIVE_EVAL_PURGE_ALLOWED"),
        tenant_ids=_parse_csv_set(os.environ.get("LIVE_EVAL_TENANT_IDS", "")),
        sender_emails=_parse_csv_set(os.environ.get("LIVE_EVAL_SENDER_EMAILS", "")),
        recipient_emails=_parse_csv_set(os.environ.get("LIVE_EVAL_RECIPIENT_EMAILS", "")),
        reply_domains=_parse_csv_set(os.environ.get("LIVE_EVAL_REPLY_DOMAINS", "")),
        intake_label=os.environ.get("LIVE_EVAL_GMAIL_LABEL", "krowolf-live-eval").strip()
        or "krowolf-live-eval",
        max_scenarios_per_run=int(os.environ.get("LIVE_EVAL_MAX_SCENARIOS_PER_RUN", "1")),
        max_gmail_sends_per_run=int(os.environ.get("LIVE_EVAL_MAX_GMAIL_SENDS", "1")),
        max_gmail_replies_per_run=int(os.environ.get("LIVE_EVAL_MAX_GMAIL_REPLIES", "0")),
        max_llm_calls_per_run=int(os.environ.get("LIVE_EVAL_MAX_LLM_CALLS", "20")),
        max_runtime_minutes=int(os.environ.get("LIVE_EVAL_MAX_RUNTIME_MINUTES", "30")),
        storage_root=storage_root,
        env_fingerprint=fingerprint,
        external_side_effects_enabled=_env_truthy("EXTERNAL_SIDE_EFFECT_TESTS"),
        sender_eval_label=os.environ.get("LIVE_EVAL_SENDER_GMAIL_LABEL", "krowolf-live-eval-sent").strip()
        or "krowolf-live-eval-sent",
        llm_provider=os.environ.get("LIVE_EVAL_LLM_PROVIDER", "").strip(),
        llm_model=os.environ.get("LIVE_EVAL_LLM_MODEL", "").strip(),
        llm_timeout=float(os.environ.get("LIVE_EVAL_LLM_TIMEOUT", "60")),
        llm_max_tokens=int(os.environ.get("LIVE_EVAL_LLM_MAX_TOKENS", "2048")),
    )
