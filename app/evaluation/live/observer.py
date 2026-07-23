"""HTTP observer client for live eval testbot."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalIntakeSkippedError
from app.evaluation.live.intake_errors import parse_intake_skipped_payload


class LiveEvalObserver:
    def __init__(
        self,
        *,
        base_url: str,
        admin_api_key: str,
        tenant_id: str,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.admin_api_key = admin_api_key
        self.tenant_id = tenant_id
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-Admin-API-Key": self.admin_api_key}

    def runtime_readiness(self) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/admin/live-eval/runtime-readiness",
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def register_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/live-eval/runs",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_run(self, evaluation_run_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/admin/live-eval/runs/{evaluation_run_id}",
            params={"tenant_id": self.tenant_id},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def poll_delivery(
        self,
        evaluation_run_id: str,
        *,
        timeout_seconds: float = 300,
        on_poll: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return self._poll(
            lambda: self.get_delivery(evaluation_run_id),
            success_predicate=lambda p: p.get("valid_count") == 1 and p.get("confirmed"),
            duplicate_predicate=lambda p: p.get("duplicate_detected"),
            timeout_seconds=timeout_seconds,
            on_poll=on_poll,
            failure_category="delivery_timeout",
        )

    def get_delivery(self, evaluation_run_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/admin/live-eval/runs/{evaluation_run_id}/delivery",
            params={"tenant_id": self.tenant_id},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def process_delivery(
        self,
        evaluation_run_id: str,
        recipient_gmail_message_id: str,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/live-eval/runs/{evaluation_run_id}/process-delivery",
            headers=self._headers(),
            json={
                "tenant_id": self.tenant_id,
                "recipient_gmail_message_id": recipient_gmail_message_id,
            },
            timeout=self.timeout,
        )
        if response.status_code == 409:
            payload = parse_intake_skipped_payload(response.json())
            if payload is not None:
                raise LiveEvalIntakeSkippedError(payload.model_dump())
        response.raise_for_status()
        return response.json()

    def get_observation(self, evaluation_run_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/admin/live-eval/runs/{evaluation_run_id}/observation",
            params={"tenant_id": self.tenant_id},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def poll_pipeline(
        self,
        evaluation_run_id: str,
        *,
        timeout_seconds: float = 600,
        on_poll: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        return self._poll(
            lambda: self.get_observation(evaluation_run_id),
            success_predicate=lambda p: (p.get("job") or {}).get("job_status") == "awaiting_approval",
            duplicate_predicate=lambda _p: False,
            timeout_seconds=timeout_seconds,
            on_poll=on_poll,
            failure_category="job_timeout",
        )

    def complete_run(self, evaluation_run_id: str, status: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/live-eval/runs/{evaluation_run_id}/status",
            headers=self._headers(),
            json={"tenant_id": self.tenant_id, "status": status},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def cleanup_recipient(
        self,
        evaluation_run_id: str,
        recipient_gmail_message_id: str,
        *,
        phase: str = "post_claim",
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/admin/live-eval/runs/{evaluation_run_id}/cleanup-recipient",
            headers=self._headers(),
            json={
                "tenant_id": self.tenant_id,
                "recipient_gmail_message_id": recipient_gmail_message_id,
                "phase": phase,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _poll(
        self,
        fetch: Callable[[], dict[str, Any]],
        *,
        success_predicate: Callable[[dict[str, Any]], bool],
        duplicate_predicate: Callable[[dict[str, Any]], bool],
        timeout_seconds: float,
        on_poll: Callable[[dict[str, Any]], None] | None,
        failure_category: str,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        delay = 2.0
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = fetch()
            if on_poll:
                on_poll(last)
            if duplicate_predicate(last):
                raise RuntimeError("correlation_failure: duplicate detected")
            if success_predicate(last):
                return last
            time.sleep(delay)
            delay = min(delay * 1.5, 30.0)
        raise TimeoutError(failure_category)
