"""
WorkflowScannerEngine

Knows which scanner adapters are registered, runs them on demand, and
persists normalised results into tenant memory (settings.memory.system_map
and settings.workflow_scan) without clobbering other settings keys.

Future adapters (monday, microsoft_mail, visma, fortnox, crm) are added by
registering them in ADAPTER_REGISTRY — no other changes required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.workflows.scanners.base import BaseWorkflowScannerAdapter, ScanResult
from app.workflows.scanners.gmail_adapter import GmailWorkflowScannerAdapter
from app.workflows.scanners.monday_adapter import MondayWorkflowScannerAdapter

# ---------------------------------------------------------------------------
# Registry — add new adapters here
# ---------------------------------------------------------------------------

ADAPTER_REGISTRY: dict[str, BaseWorkflowScannerAdapter] = {
    "gmail":  GmailWorkflowScannerAdapter(),
    "monday": MondayWorkflowScannerAdapter(),
    # "microsoft_mail": MicrosoftMailScannerAdapter(),      # future
    # "visma":          VismaScannerAdapter(),               # future
    # "fortnox":        FortnoxScannerAdapter(),             # future
}


def list_supported_systems() -> list[str]:
    """Return sorted list of registered system keys."""
    return sorted(ADAPTER_REGISTRY.keys())


class WorkflowScannerEngine:
    """
    Orchestrates scanner adapter execution and settings persistence.

    Usage
    -----
    engine = WorkflowScannerEngine(db, tenant_id, settings_repo)
    result = engine.run("gmail")
    """

    def __init__(self, db: Any, tenant_id: str, settings_repo: Any):
        self._db = db
        self._tenant_id = tenant_id
        self._repo = settings_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, system: str) -> ScanResult:
        """
        Run the adapter for `system`, persist results, return ScanResult.

        On failure the existing tenant memory is preserved untouched;
        workflow_scan.status is set to "failed" with a safe error message.
        Raises RuntimeError so callers can map it to an HTTP response.
        """
        if system not in ADAPTER_REGISTRY:
            raise KeyError(f"No scanner registered for system '{system}'")

        adapter = ADAPTER_REGISTRY[system]
        existing = self._repo.get_settings(self._db, self._tenant_id)

        try:
            result = adapter.run(self._db, self._tenant_id)
        except Exception as exc:
            result = ScanResult(
                system=system,
                status="failed",
                scanned_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc)[:200],
            )
            self._persist(existing, result, preserve_memory=True)
            raise RuntimeError(f"{system} scan failed: {str(exc)[:200]}") from exc

        if result.status == "failed":
            self._persist(existing, result, preserve_memory=True)
            raise RuntimeError(f"{system} scan failed: {result.error or 'unknown error'}")

        self._persist(existing, result, preserve_memory=False)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _persist(
        self,
        existing_settings: dict,
        result: ScanResult,
        preserve_memory: bool,
    ) -> None:
        """Write scan result into settings, merging safely."""
        from app.main import _get_memory  # imported here to avoid circular import

        updated = dict(existing_settings)
        current_memory = _get_memory(existing_settings)

        if not preserve_memory and result.data:
            # Update only this system's slot in system_map
            current_memory["system_map"][result.system] = result.data

        updated["memory"] = current_memory

        # Merge scan state into workflow_scan (preserve other systems' summaries)
        prev_scan = dict(existing_settings.get("workflow_scan") or {})
        prev_summary = dict(prev_scan.get("summary") or {})

        if result.status == "failed":
            prev_summary[result.system] = {"error": result.error}
        else:
            prev_summary[result.system] = result.summary

        # Rebuild systems_scanned as union of previously scanned + current
        prev_systems: list[str] = list(prev_scan.get("systems_scanned") or [])
        if result.system not in prev_systems:
            prev_systems.append(result.system)

        updated["workflow_scan"] = {
            "last_scan_at":    result.scanned_at,
            "systems_scanned": prev_systems,
            "status":          result.status,
            "summary":         prev_summary,
        }

        self._repo.update_settings(self._db, self._tenant_id, updated)
