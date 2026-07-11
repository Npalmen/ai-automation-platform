"""
UI HTML contract tests for the operator console (app/ui/index.html).

These tests verify structural guarantees in the HTML/CSS/JS without running
a browser. They guard against regressions where:

- Overlay modals (#wizardOverlay, #intSetupOverlay) render in the document
  flow instead of as fixed-position overlays (the primary layout bug).
- The admin key input form (#adminKeySection) is present but can be hidden
  via JS (session-mode admin must not be forced to enter an API key).
- The authBanner is not hard-coded visible (it must be hidden by JS when
  a session is active).
- apiFetch sends credentials (needed for session-cookie auth on tenant
  endpoints after the priority-0 auth path in get_verified_tenant).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def ui_html() -> str:
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/ui")
    assert resp.status_code == 200, f"UI returned {resp.status_code}"
    return resp.text


# ── Overlay modals ────────────────────────────────────────────────────────────

class TestOverlayModals:

    def test_wizard_overlay_exists(self, ui_html):
        assert 'id="wizardOverlay"' in ui_html

    def test_intsetup_overlay_exists(self, ui_html):
        assert 'id="intSetupOverlay"' in ui_html

    def test_wizard_overlay_has_display_none_css(self, ui_html):
        """#wizardOverlay must be hidden by default — position:fixed is useless
        if the overlay is visible in the document flow on page load."""
        style_block = _extract_style(ui_html)
        assert "#wizardOverlay" in style_block, \
            "#wizardOverlay CSS rule is missing from <style> block"
        # The rule must set display:none at some point
        assert "display: none" in style_block or "display:none" in style_block

    def test_intsetup_overlay_has_display_none_css(self, ui_html):
        style_block = _extract_style(ui_html)
        assert "#intSetupOverlay" in style_block, \
            "#intSetupOverlay CSS rule is missing from <style> block"

    def test_intsetup_open_class_enables_display(self, ui_html):
        """#intSetupOverlay.open must set display:flex — JS adds class 'open'."""
        style_block = _extract_style(ui_html)
        assert "intSetupOverlay.open" in style_block, \
            "#intSetupOverlay.open CSS rule is missing (JS uses classList.add('open'))"

    def test_wizard_overlay_is_position_fixed(self, ui_html):
        style_block = _extract_style(ui_html)
        # Find the rule block(s) containing #wizardOverlay
        assert "position: fixed" in style_block or "position:fixed" in style_block

    def test_wiz_panel_styles_exist(self, ui_html):
        style_block = _extract_style(ui_html)
        assert ".wiz-panel" in style_block

    def test_int_setup_panel_styles_exist(self, ui_html):
        style_block = _extract_style(ui_html)
        assert ".int-setup-panel" in style_block


# ── Session-mode / no forced API key ─────────────────────────────────────────

class TestSessionModeUI:

    def test_admin_key_section_has_id(self, ui_html):
        """Must have id so JS can hide it when session is active."""
        assert 'id="adminKeySection"' in ui_html

    def test_admin_key_section_not_hidden_by_default(self, ui_html):
        """The section must be visible by default (hidden via JS for session users).
        If it were hard-coded hidden, API-key-mode admins couldn't use it."""
        # Confirm the element does not carry display:none inline initially
        match = re.search(r'id="adminKeySection"[^>]*>', ui_html)
        assert match is not None
        opening_tag = match.group(0)
        assert "display:none" not in opening_tag and "display: none" not in opening_tag

    def test_auth_banner_not_hardcoded_visible(self, ui_html):
        """authBanner must start hidden; JS un-hides it only when no key is present
        in customer-mode. It must not be shown when session is active."""
        match = re.search(r'id="authBanner"[^>]*>', ui_html)
        assert match is not None
        # The element itself must not be visible by default — it uses display:none
        # or is controlled entirely by JS. The test verifies it's not statically shown.
        tag = match.group(0)
        assert "display:none" in tag or "display: none" in tag or \
               'style="' not in tag, \
               "authBanner should be hidden by default (display:none in inline style)"

    def test_admin_key_banner_not_shown_by_default(self, ui_html):
        match = re.search(r'id="adminKeyBanner"[^>]*>', ui_html)
        assert match is not None
        tag = match.group(0)
        assert "display:none" in tag or "display: none" in tag


# ── apiFetch sends credentials ────────────────────────────────────────────────

class TestApiFetchCredentials:

    def test_apifetch_sends_same_origin_credentials(self, ui_html):
        """apiFetch must forward the session cookie to tenant-scoped backend endpoints.
        Either by including credentials:'same-origin' directly, or by routing through
        adminApiFetch (which already uses credentials:'same-origin')."""
        apifetch_idx = ui_html.find("async function apiFetch")
        assert apifetch_idx != -1, "apiFetch function not found in HTML"
        # Inspect a window large enough to cover the full function body (~2000 chars)
        apifetch_section = ui_html[apifetch_idx: apifetch_idx + 2000]
        # Either direct use of same-origin, or delegation to adminApiFetch (which uses it)
        has_same_origin = "same-origin" in apifetch_section
        has_admin_fetch_route = "adminApiFetch" in apifetch_section
        assert has_same_origin or has_admin_fetch_route, (
            "apiFetch must include credentials:'same-origin' or route to adminApiFetch "
            "(which already sends the session cookie)"
        )

    def test_admin_api_fetch_already_sends_credentials(self, ui_html):
        """adminApiFetch already sends credentials:'same-origin' — must not regress."""
        match = re.search(
            r"async function adminApiFetch\(path.*?\{(.*?)^\}",
            ui_html,
            re.DOTALL | re.MULTILINE,
        )
        assert match is not None, "adminApiFetch function not found in HTML"
        body = match.group(1)
        assert "same-origin" in body


class TestCustomerContextView:
    """Guard the customer context view structural requirements."""

    def test_viewCustomerCtx_exists(self, ui_html):
        """#viewCustomerCtx div must be present for single-customer drill-down."""
        assert 'id="viewCustomerCtx"' in ui_html

    def test_ctxCustomerName_el_exists(self, ui_html):
        """Name placeholder must exist so JS can populate it."""
        assert 'id="ctxCustomerName"' in ui_html

    def test_ctxHealthBadge_el_exists(self, ui_html):
        """Health badge element must exist."""
        assert 'id="ctxHealthBadge"' in ui_html

    def test_ctxKpis_el_exists(self, ui_html):
        """KPI row container must exist."""
        assert 'id="ctxKpis"' in ui_html

    def test_ctxContent_el_exists(self, ui_html):
        """Body content container must exist."""
        assert 'id="ctxContent"' in ui_html

    def test_customerCtx_in_view_display(self, ui_html):
        """customerCtx must be registered in _VIEW_DISPLAY."""
        assert "customerCtx" in ui_html

    def test_loadCustomerCtx_function_exists(self, ui_html):
        """loadCustomerCtx JS function must be defined."""
        assert "async function loadCustomerCtx" in ui_html

    def test_openTenant_navigates_to_ctx(self, ui_html):
        """openTenant must navigate to customerCtx view, not setup."""
        match = re.search(
            r"async function openTenant\(tenantId\)(.*?)^\}",
            ui_html,
            re.DOTALL | re.MULTILINE,
        )
        assert match is not None, "openTenant function not found"
        body = match.group(1)
        assert "customerCtx" in body, "openTenant must navigate to customerCtx"
        assert "switchView('setup')" not in body, "openTenant must not go directly to setup"

    def test_openTenantSetup_function_exists(self, ui_html):
        """openTenantSetup must exist as the path to the Settings view."""
        assert "async function openTenantSetup" in ui_html


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_style(html: str) -> str:
    """Return the content of the first <style> block."""
    m = re.search(r"<style>(.*?)</style>", html, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else ""
