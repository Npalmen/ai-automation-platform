"""Active customer settings — post-activation configuration edits."""

from app.admin.customer_settings.service import (
    get_customer_settings_view,
    get_domain_settings,
    patch_domain_settings,
    preview_domain_settings,
)

__all__ = [
    "get_customer_settings_view",
    "get_domain_settings",
    "patch_domain_settings",
    "preview_domain_settings",
]
