"""Focused tests for R5 profile-driven digital coworker reply quality closure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.profile_testbot.constants import QUALIFICATION_COWORKER_REPLY
from app.evaluation.profile_testbot.qualification.coworker_reply_quality_closure import (
    R5_QUALIFYING_EXECUTOR_SHA,
    R5_QUALIFYING_RELEASE_GATE_RUN,
    R5_R4_PASS_CAMPAIGN_ID,
    R5_QUARANTINED_CAMPAIGN_IDS,
    evaluate_r5_closure_evidence,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
)
from app.evaluation.regression.qualification_registry import qualification_index

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "storage" / "status"


def _valid_pass_record() -> dict:
    return json.loads(
        (STATUS / "digital-coworker-r4-attempt12-pass-record-4ad74d4.json").read_text(
            encoding="utf-8"
        )
    )


def _valid_execution() -> dict:
    return json.loads(
        (STATUS / "digital-coworker-r4-live-execution-4ad74d4.json").read_text(encoding="utf-8")
    )


class TestR5ClosureEvidence:
    def test_valid_frozen_evidence_passes_without_r1_rerun(self):
        result = evaluate_r5_closure_evidence(
            repo_root=ROOT,
            run_r1_hermetic=False,
            pass_record=_valid_pass_record(),
            execution_report=_valid_execution(),
        )
        assert result.passed, result.blockers
        assert result.gates["R2_HUMAN_REVIEW"] == "PASS"
        assert result.gates["R3_LIVE_CANARY"] == "PASS"
        assert result.gates["R4_LIVE_CAMPAIGN"] == "PASS"
        assert result.gates["automatic_gmail"] == "false"
        assert result.gates["production_activation"] == "false"

    def test_missing_r4_pass_record_blocked(self):
        result = evaluate_r5_closure_evidence(
            repo_root=ROOT,
            run_r1_hermetic=False,
            pass_record={"overall_status": "FAIL"},
            execution_report=_valid_execution(),
        )
        assert not result.passed
        assert "r4_pass_record_not_pass" in result.blockers

    def test_wrong_campaign_blocked(self):
        bad = _valid_pass_record()
        bad["campaign_id"] = "00000000-0000-0000-0000-000000000000"
        result = evaluate_r5_closure_evidence(
            repo_root=ROOT,
            run_r1_hermetic=False,
            pass_record=bad,
            execution_report=_valid_execution(),
        )
        assert not result.passed
        assert "r4_campaign_id_mismatch" in result.blockers

    def test_quarantined_campaign_cannot_be_pass_campaign(self):
        assert R5_R4_PASS_CAMPAIGN_ID not in R5_QUARANTINED_CAMPAIGN_IDS
        for cid in R5_QUARANTINED_CAMPAIGN_IDS:
            bad = _valid_pass_record()
            bad["campaign_id"] = cid
            result = evaluate_r5_closure_evidence(
                repo_root=ROOT,
                run_r1_hermetic=False,
                pass_record=bad,
                execution_report=_valid_execution(),
            )
            assert not result.passed

    def test_hash_mismatch_blocked(self):
        bad = _valid_pass_record()
        bad["candidate_runtime_sha"] = "0" * 40
        result = evaluate_r5_closure_evidence(
            repo_root=ROOT,
            run_r1_hermetic=False,
            pass_record=bad,
            execution_report=_valid_execution(),
        )
        assert not result.passed
        assert "r4_candidate_sha_mismatch" in result.blockers

    def test_repeated_evaluation_is_stable(self):
        kwargs = {
            "repo_root": ROOT,
            "run_r1_hermetic": False,
            "pass_record": _valid_pass_record(),
            "execution_report": _valid_execution(),
        }
        first = evaluate_r5_closure_evidence(**kwargs)
        second = evaluate_r5_closure_evidence(**kwargs)
        assert first.passed and second.passed
        assert first.blockers == second.blockers

    def test_conflicting_registry_valid_provenance_blocked(self, monkeypatch):
        entry = dict(qualification_index()[QUALIFICATION_COWORKER_REPLY])
        entry["status"] = "VALID"
        entry["source_sha"] = "deadbeef"
        entry["source_workflow_run"] = "99999"

        def _fake_index():
            idx = qualification_index()
            return {**idx, QUALIFICATION_COWORKER_REPLY: entry}

        monkeypatch.setattr(
            "app.evaluation.profile_testbot.qualification.coworker_reply_quality_closure.qualification_index",
            _fake_index,
        )
        result = evaluate_r5_closure_evidence(
            repo_root=ROOT,
            run_r1_hermetic=False,
            pass_record=_valid_pass_record(),
            execution_report=_valid_execution(),
            allow_registry_already_valid=True,
        )
        assert not result.passed
        assert "registry_conflicting_valid_provenance" in result.blockers

    def test_r1_hermetic_passes_when_run(self):
        result = evaluate_r5_closure_evidence(
            repo_root=ROOT,
            run_r1_hermetic=True,
            pass_record=_valid_pass_record(),
            execution_report=_valid_execution(),
        )
        assert result.gates["R1_HERMETIC"] == "PASS"
        assert result.passed, result.blockers


class TestR5RegistryTargetConstants:
    def test_locked_registry_provenance_constants(self):
        assert R5_QUALIFYING_EXECUTOR_SHA == "4ad74d4ac19011d5edfb8ea160112f649052422d"
        assert R5_QUALIFYING_RELEASE_GATE_RUN == "31220948265"
        assert R4_LOCKED_CANDIDATE_RUNTIME_SHA.startswith("b7fd95e")
