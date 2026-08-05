"""Trusted immutable R4 reviewed-body snapshot for live runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class R4ReviewedBodySnapshot:
    campaign_type: str
    execution_mode: str
    scenario_id: str
    candidate_runtime_sha: str
    executor_runtime_sha: str
    manifest_semantic_hash: str
    candidate_package_semantic_hash: str
    human_review_artifact_hash: str
    plan_hash: str
    reviewed_body: str
    reviewed_body_hash: str
    review_status: str
    renderer_type: str
    model_id: str | None
    prompt_version: str | None
    recipient: str
    campaign_id: str
    evaluation_run_id: str
    immutable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "R4ReviewedBodySnapshot":
        return cls(
            campaign_type=str(raw["campaign_type"]),
            execution_mode=str(raw["execution_mode"]),
            scenario_id=str(raw["scenario_id"]),
            candidate_runtime_sha=str(raw["candidate_runtime_sha"]),
            executor_runtime_sha=str(raw["executor_runtime_sha"]),
            manifest_semantic_hash=str(raw["manifest_semantic_hash"]),
            candidate_package_semantic_hash=str(raw["candidate_package_semantic_hash"]),
            human_review_artifact_hash=str(raw["human_review_artifact_hash"]),
            plan_hash=str(raw["plan_hash"]),
            reviewed_body=str(raw["reviewed_body"]),
            reviewed_body_hash=str(raw["reviewed_body_hash"]),
            review_status=str(raw["review_status"]),
            renderer_type=str(raw["renderer_type"]),
            model_id=raw.get("model_id"),
            prompt_version=raw.get("prompt_version"),
            recipient=str(raw["recipient"]),
            campaign_id=str(raw["campaign_id"]),
            evaluation_run_id=str(raw["evaluation_run_id"]),
            immutable=bool(raw.get("immutable", True)),
        )


def validate_r4_snapshot_for_reply(
    snapshot: R4ReviewedBodySnapshot,
    *,
    expected_body_hash: str,
    send_scenario_ids: set[str] | frozenset[str],
    recipient: str,
    blocking_notes: list[str] | None = None,
) -> list[str]:
    blockers: list[str] = []
    if not snapshot.immutable:
        blockers.append("snapshot_not_immutable")
    if snapshot.scenario_id not in send_scenario_ids:
        blockers.append("scenario_not_in_r4_send_registry")
    if snapshot.reviewed_body_hash != expected_body_hash:
        blockers.append("body_hash_mismatch")
    if snapshot.review_status not in {"PASS", "PASS_WITH_NOTE"}:
        blockers.append(f"review_status_not_accepted:{snapshot.review_status}")
    if blocking_notes:
        blockers.append("blocking_notes_present")
    if snapshot.recipient.strip().lower() != recipient.strip().lower():
        blockers.append("recipient_mismatch")
    if snapshot.renderer_type != "constrained_llm_v1":
        blockers.append("renderer_type_mismatch")
    return blockers


def embed_r4_snapshot_in_live_eval(input_data: dict[str, Any], snapshot: R4ReviewedBodySnapshot) -> dict[str, Any]:
    """Attach trusted snapshot under live_eval without mutating prior keys unexpectedly."""
    out = dict(input_data or {})
    live = dict(out.get("live_eval") or {})
    if "r4_reviewed_body_snapshot" in live and live["r4_reviewed_body_snapshot"] != snapshot.to_dict():
        raise ValueError("r4_reviewed_body_snapshot_immutable_violation")
    live["r4_reviewed_body_snapshot"] = snapshot.to_dict()
    out["live_eval"] = live
    return out
