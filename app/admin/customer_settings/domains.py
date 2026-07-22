"""Settings domain registry, permissions, and forbidden write paths."""

from __future__ import annotations

from typing import Any, Literal

from app.core.admin_session import OperatorIdentity

SettingsDomain = Literal[
    "identity",
    "modules",
    "services",
    "integrations",
    "routing",
    "automation",
    "intake",
]

SETTINGS_DOMAINS: frozenset[str] = frozenset(
    {"identity", "modules", "services", "integrations", "routing", "automation", "intake"}
)

# Legacy section names map 1:1 to domains for backward-compatible routes.
LEGACY_SECTION_ALIASES: dict[str, str] = {
    "identity": "identity",
    "modules": "modules",
    "services": "services",
    "integrations": "integrations",
    "routing": "routing",
    "automation": "automation",
    "intake": "intake",
}

RESERVED_INTERNAL_SETTINGS_KEYS: frozenset[str] = frozenset({"_readiness"})

FORBIDDEN_PATCH_KEYS: frozenset[str] = RESERVED_INTERNAL_SETTINGS_KEYS | frozenset(
    {
        "allowed_integrations",
        "enabled_job_types",
        "enabled_external_writes",
        "auto_actions",
        "effective_policy_snapshot",
        "config_version",
        "readiness_config_version",
        "readiness_checked_at",
        "oauth_credentials",
        "credentials",
        "activation_snapshot",
        "snapshot_json",
        "scheduler",
        "lifecycle_status",
        "status",
    }
)

READINESS_DOMAINS_BY_SETTINGS_DOMAIN: dict[str, tuple[str, ...]] = {
    "identity": ("identity",),
    "modules": ("modules", "integrations"),
    "services": ("services", "routing"),
    "integrations": ("integrations", "finance_destination"),
    "routing": ("routing", "finance_destination"),
    "automation": ("automation",),
    "intake": ("intake",),
}


def normalize_domain(domain_or_section: str) -> str:
    key = (domain_or_section or "").strip().lower()
    if key not in SETTINGS_DOMAINS:
        raise ValueError(f"Unknown settings domain: {domain_or_section}")
    return key


def domain_permissions(operator: OperatorIdentity) -> dict[str, dict[str, bool]]:
    role = operator.get("role") or "read_only"
    perms: dict[str, dict[str, bool]] = {}
    for domain in sorted(SETTINGS_DOMAINS):
        can_read = role in {"read_only", "operations", "admin", "super_admin"}
        can_write = _can_write_domain(role, domain)
        perms[domain] = {
            "read": can_read,
            "write": can_write,
            "preview": can_write,
        }
    return perms


def assert_domain_permission(
    operator: OperatorIdentity,
    domain: str,
    action: Literal["read", "write", "preview"],
) -> None:
    perms = domain_permissions(operator).get(domain)
    if not perms or not perms.get(action, False):
        raise PermissionError(f"Operator role may not {action} domain '{domain}'.")


def _can_write_domain(role: str, domain: str) -> bool:
    if role in {"admin", "super_admin"}:
        return True
    if role == "operations":
        return domain == "routing"
    return False


def collect_forbidden_keys(payload: dict[str, Any], *, prefix: str = "") -> list[str]:
    found: list[str] = []
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in FORBIDDEN_PATCH_KEYS:
            found.append(path)
        if isinstance(value, dict):
            found.extend(collect_forbidden_keys(value, prefix=path))
    return found
