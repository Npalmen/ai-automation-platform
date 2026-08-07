"""Read-only thread-evidence contract probe — fake Gmail objects, no writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

INBOUND_RFC = "inbound-anchor@mail.test"
PROVIDER_RFC = "provider-reply@mail.test"
UNRELATED_RFC = "unrelated@mail.test"


def _thread_evidence_contract_probe() -> dict:
    from app.evaluation.live.gmail_transport import (
        ExpectedReplyEvidence,
        ProviderSentObjectEvidence,
        compute_reply_thread_match,
    )

    provider_sent = ProviderSentObjectEvidence(
        message_id="provider-msg-positive",
        thread_id="thread-inbound",
        rfc_message_id=PROVIDER_RFC,
        in_reply_to=INBOUND_RFC,
        references=f"<{INBOUND_RFC}>",
        labels=("SENT",),
        in_sent=True,
        to_recipients=("sender@eval.test",),
        from_email="recipient@eval.test",
        reply_to=None,
        subject_truncated="Re: probe",
    )
    delivered = ExpectedReplyEvidence(
        message_id="delivered-copy",
        subject_truncated="Re: probe",
        from_masked="r***@eval.test",
        internal_date_ms=1,
        rfc_message_id=PROVIDER_RFC,
        in_reply_to=INBOUND_RFC,
    )
    positive_ok, positive_basis = compute_reply_thread_match(
        provider_sent=provider_sent,
        inbound_rfc_message_id=INBOUND_RFC,
        inbound_gmail_thread_id="thread-inbound",
        delivered=delivered,
    )
    negative_provider = ProviderSentObjectEvidence(
        message_id="provider-msg-negative",
        thread_id="thread-other",
        rfc_message_id="wrong-chain@mail.test",
        in_reply_to=UNRELATED_RFC,
        references=f"<{UNRELATED_RFC}>",
        labels=("SENT",),
        in_sent=True,
        to_recipients=("sender@eval.test",),
        from_email="recipient@eval.test",
        reply_to=None,
        subject_truncated="Re: probe",
    )
    negative_ok, negative_basis = compute_reply_thread_match(
        provider_sent=negative_provider,
        inbound_rfc_message_id=INBOUND_RFC,
        delivered=ExpectedReplyEvidence(
            message_id="delivered-bad",
            subject_truncated="Re",
            from_masked="r***@eval.test",
            internal_date_ms=1,
            rfc_message_id="wrong-chain@mail.test",
        ),
    )
    bool_rfc_bug = bool(PROVIDER_RFC) and not positive_ok
    return {
        "provider_message_id": provider_sent.message_id,
        "provider_sent_object_present": True,
        "provider_rfc_message_id": provider_sent.rfc_message_id,
        "delivered_copy_rfc_message_id": delivered.rfc_message_id,
        "delivered_rfc_matches_provider": delivered.rfc_message_id == provider_sent.rfc_message_id,
        "inbound_rfc_message_id": INBOUND_RFC,
        "inbound_linkage_in_reply_to": provider_sent.in_reply_to == INBOUND_RFC,
        "positive_thread_match": positive_ok,
        "positive_thread_match_basis": positive_basis,
        "negative_thread_match": negative_ok,
        "negative_thread_match_basis": negative_basis,
        "rejects_bool_rfc_only_semantics": not bool_rfc_bug,
        "passed": (
            positive_ok
            and positive_basis in {"rfc_in_reply_to", "combination"}
            and not negative_ok
            and delivered.rfc_message_id == provider_sent.rfc_message_id
        ),
    }


def main() -> int:
    runtime = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    probe = _thread_evidence_contract_probe()
    report = {
        "runtime_sha": runtime,
        "thread_evidence_contract_probe": probe,
        "passed": probe.get("passed"),
        "execute_not_run": True,
        "gmail_writes": 0,
    }
    short = runtime[:7] if runtime != "unknown" else "local"
    for base in (ROOT / "storage" / "status", Path(r"C:\ai_automation_platform\storage\status")):
        base.mkdir(parents=True, exist_ok=True)
        (base / f"r4-thread-evidence-contract-probe-{short}.json").write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2))
    return 0 if probe.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
