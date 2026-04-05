from contextvars import ContextVar

_current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: str) -> None:
    _current_tenant.set(tenant_id)


def get_current_tenant() -> str:
    tenant = _current_tenant.get()
    if tenant is None:
        raise RuntimeError("Ingen tenant är satt i aktuell kontext.")
    return tenant