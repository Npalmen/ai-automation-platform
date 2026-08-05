"""Focused R4 campaign contract / coverage / dry-run tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (
    generate_r4_candidates,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_contract import (
    validate_r4_registration_contract,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_execution import (
    run_r4_live_campaign,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
    build_r4_human_review_package,
    validate_r4_human_review_bindings,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_manifest import (
    build_r4_campaign_manifest,
    compute_r4_semantic_manifest_hash,
    validate_r4_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_readiness import (
    evaluate_coworker_r4_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R3_QUALIFYING_SHA,
    R4_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_SERVICE_PREQUAL_IDS,
)


def test_r4_registry_coverage_locked():
    assert len(R4_SCENARIO_IDS) == 36
    assert len(R4_SEND_SCENARIO_IDS) == 20
    assert len(R4_NO_SEND_SCENARIO_IDS) == 16
    assert len(R4_SERVICE_PREQUAL_IDS) >= 10
    assert len(set(R4_SCENARIO_IDS)) == 36


def test_r4_manifest_stable_and_not_r3_frozen():
    m1 = build_r4_campaign_manifest(runtime_sha=R3_QUALIFYING_SHA)
    m2 = build_r4_campaign_manifest(runtime_sha=R3_QUALIFYING_SHA)
    assert m1["manifest_semantic_hash"] == m2["manifest_semantic_hash"]
    assert m1["campaign_type"] == R4_LIVE_QUALITY_CAMPAIGN_TYPE
    assert m1["execution_mode"] == R4_EXECUTION_MODE
    assert m1["ai_mode"] == R4_AI_MODE
    assert m1["automatic_gmail"] is False
    assert m1["production_activation"] is False
    assert m1["no_automatic_retry"] is True
    assert m1["no_drafts"] is True
    assert m1["r3_hold_override_generalized"] is False
    assert not validate_r4_manifest(m1)
    assert (
        compute_r4_semantic_manifest_hash(m1["semantic_payload"])
        == m1["manifest_semantic_hash"]
    )
    coverage = m1["coverage"]
    assert coverage["scenario_count"] == 36
    assert coverage["coworker_family_count"] >= 15
    assert coverage["planned_sends"] == 20
    assert coverage["planned_no_send"] >= 16
    assert coverage["multi_turn_count"] >= 10
    assert coverage["no_name_phone_count"] >= 10
    assert coverage["service_prequalification_count"] >= 10


def test_r4_contract_rejects_r3_frozen_and_hold_override():
    ok = validate_r4_registration_contract(
        tenant_id="TENANT_LIVE_EVAL",
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=R4_EXECUTION_MODE,
        ai_mode=R4_AI_MODE,
        scenario_ids=list(R4_SCENARIO_IDS),
        env="test",
    )
    assert ok.valid
    bad = validate_r4_registration_contract(
        tenant_id="TENANT_LIVE_EVAL",
        campaign_type="coworker_r3_frozen_live_canary",
        execution_mode="r3_frozen_approved_body",
        ai_mode="fixture_ai",
        apply_r3_hold_override=True,
        automatic_gmail=True,
        production_activation=True,
    )
    assert not bad.valid
    joined = " ".join(bad.blockers)
    assert "R3" in joined or "forbidden" in joined
    assert "hold override" in joined
    assert "automatic_gmail" in joined


def test_r4_candidates_write_free_and_body_hashes(tmp_path: Path):
    result = generate_r4_candidates(runtime_sha=R3_QUALIFYING_SHA)
    assert result["gmail_sends"] == 0
    assert result["gmail_drafts"] == 0
    assert result["external_writes"] == 0
    assert result["send_candidate_count"] == 20
    assert result["no_send_candidate_count"] == 16
    assert result["r3_hold_override_generalized"] is False
    assert result["human_review_complete"] is False
    for row in result["send_candidates"]:
        assert row.get("body_hash")
        assert row.get("r3_hold_override_applied") is False
        assert "rendered_body" in row
    # Complaint scenario must not silently inherit R3 override.
    c088 = next(r for r in result["send_candidates"] if r["scenario_id"] == "PTB-DCQ-0088")
    assert c088["r3_hold_override_applied"] is False
    assert result["overall_status"] in {"PASS", "BLOCKED"}
    if result["overall_status"] != "PASS":
        # Still require structural integrity even if oracle blockers exist.
        assert all(r.get("body_hash") for r in result["send_candidates"])


def test_r4_human_review_pending_by_default():
    candidates = generate_r4_candidates(runtime_sha=R3_QUALIFYING_SHA)
    package = build_r4_human_review_package(candidates, runtime_sha=R3_QUALIFYING_SHA)
    assert package["human_review_complete"] is False
    assert package["send_review_count"] == len(candidates["send_candidates"])
    assert all(r["review_status"] == "PENDING" for r in package["reviews"])
    state = validate_r4_human_review_bindings(candidates, package)
    assert state["human_review_complete"] is False
    assert state["pending_reviews"] == package["send_review_count"]


def test_r4_readiness_and_dry_run_no_execute(tmp_path: Path):
    manifest = build_r4_campaign_manifest(runtime_sha=R3_QUALIFYING_SHA)
    candidates = generate_r4_candidates(runtime_sha=R3_QUALIFYING_SHA)
    review = build_r4_human_review_package(candidates, runtime_sha=R3_QUALIFYING_SHA)
    ready = evaluate_coworker_r4_readiness(
        runtime_sha=R3_QUALIFYING_SHA,
        manifest=manifest,
        candidates=candidates,
        human_review=review,
        skip_live_probes=True,
    )
    assert ready["r3_prerequisite_pass"] is True
    assert ready["manual_execution_confirmation_required"] is True
    assert ready["r4_campaign_ready_for_manual_execution"] is False

    result = run_r4_live_campaign(
        mode="dry_run",
        expected_runtime_sha=R3_QUALIFYING_SHA,
        status_dir=tmp_path,
    )
    assert result["gmail_sends"] == 0
    assert result["gmail_drafts"] == 0
    assert result["external_writes"] == 0
    assert result["new_trigger_emails"] == 0
    assert result["automatic_gmail"] is False
    assert result["production_activation"] is False
    # Dry-run may PASS or BLOCKED depending on oracle/candidate status; never sends.
    assert result["overall_status"] in {"PASS", "BLOCKED"}
    assert (tmp_path / f"digital-coworker-r4-manifest-{R3_QUALIFYING_SHA[:7]}.json").is_file()

    stopped = run_r4_live_campaign(
        mode="execute",
        expected_runtime_sha=R3_QUALIFYING_SHA,
        status_dir=tmp_path,
    )
    assert stopped["overall_status"] == "STOPPED"
    assert stopped["gmail_sends"] == 0
