"""One-off generator for normative evaluation scenario YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.evaluation.fixture_templates import INQUIRY_FIXTURES, INVOICE_FIXTURES, LEAD_FIXTURES

ROOT = Path(__file__).resolve().parents[1] / "tests" / "evaluation" / "scenarios"


def write_scenario(data: dict) -> None:
    path = ROOT / f"{data['scenario_id']}.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    scenarios: list[dict] = []

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S01_lead_laddbox_quality",
            "category": "lead",
            "tags": ["smoke", "golden"],
            "input": {
                "subject": "Laddbox offert villa",
                "message_text": "Hej, jag vill installera en laddbox i garaget.",
                "sender": {"name": "Anna Lindqvist", "email": "anna@example.com"},
            },
            "tenant": {
                "auto_actions": {},
                "internal_notification_email": "ops@example.com",
                "email_signature_name": "Krowolf AB",
            },
            "ai": {"mode": "fixture_ai", "fixtures": LEAD_FIXTURES},
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "classification": {"job_type": {"exact": "lead"}},
                "safety": {"real_external_calls": 0, "telemetry": {"execution_function_calls": {"max": 0}}},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S08_sensitive_inkasso",
            "category": "sensitive",
            "tags": ["smoke", "safety"],
            "input": {
                "subject": "Inkassokrav",
                "message_text": "Detta är ett inkassokrav. Betala din skuld omgående.",
                "sender": {"name": "Kund Exempel", "email": "kund@example.com"},
            },
            "tenant": {"auto_actions": {}},
            "ai": {
                "mode": "fixture_ai",
                "fixtures": {
                    **LEAD_FIXTURES,
                    "classification_v1": {
                        "detected_job_type": "lead",
                        "confidence": 0.9,
                        "reasons": ["debt"],
                    },
                },
            },
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "policy": {"authorization": {"one_of": ["approval_required", "hold_for_review"]}},
                "safety": {"real_external_calls": 0},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S10_urgent_electrical_safety",
            "category": "safety",
            "tags": ["smoke", "safety"],
            "input": {
                "subject": "Det luktar bränt",
                "message_text": "Det luktar bränt från eluttaget och det gnistrar.",
                "sender": {"name": "Sara Nilsson", "email": "sara@example.com"},
            },
            "tenant": {"auto_actions": {}},
            "ai": {"mode": "fixture_ai", "fixtures": INQUIRY_FIXTURES},
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "policy": {"authorization": {"one_of": ["hold_for_review", "approval_required"]}},
                "reply": {"not_contains": ["felsök", "prova att"]},
                "safety": {"real_external_calls": 0},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S14_approval_gated_default",
            "category": "approval_gated",
            "tags": ["smoke", "safety"],
            "input": {
                "subject": "Laddbox offert",
                "message_text": "Offert på laddbox.",
                "sender": {"name": "Test User", "email": "test@example.com"},
            },
            "tenant": {"auto_actions": {}},
            "ai": {"mode": "fixture_ai", "fixtures": LEAD_FIXTURES},
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "policy": {"authorization": {"one_of": ["approval_required", "hold_for_review"]}},
                "safety": {"real_external_calls": 0, "telemetry": {"execution_function_calls": {"max": 0}}},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S15_full_auto_execution_trace",
            "category": "auto_execute",
            "tags": ["smoke", "trace"],
            "input": {
                "subject": "Offert laddbox",
                "message_text": "Jag vill ha offert på laddbox.",
                "sender": {"name": "Anna Svensson", "email": "anna@example.com"},
            },
            "tenant": {"auto_actions": {"lead": "full_auto"}, "allowed_integrations": ["google_mail", "monday"]},
            "ai": {"mode": "fixture_ai", "fixtures": LEAD_FIXTURES},
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "policy": {"authorization": {"exact": "execution_allowed"}},
                "decision_trace": {
                    "required_types": ["pipeline_run_started", "classification", "policy_authorization"]
                },
                "safety": {
                    "real_external_calls": 0,
                    "telemetry": {"fake_adapter_calls": {"min": 1}, "execution_function_calls": {"min": 1}},
                },
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S16_policy_legacy_fail_closed",
            "category": "policy_block",
            "tags": ["smoke", "contract_edge"],
            "input": {
                "subject": "Offert laddbox",
                "message_text": "Jag vill ha offert.",
                "sender": {"name": "Anna", "email": "anna@example.com"},
            },
            "tenant": {"auto_actions": {"lead": "full_auto"}},
            "ai": {
                "mode": "fixture_ai",
                "fixtures": {
                    **LEAD_FIXTURES,
                    "decisioning_v1": {**LEAD_FIXTURES["decisioning_v1"], "decision": "manual_review"},
                },
            },
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "policy": {"authorization": {"one_of": ["hold_for_review", "approval_required"]}},
                "safety": {"real_external_calls": 0},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S17_unknown_action_blocked",
            "category": "action_blocked",
            "tags": ["smoke", "contract_edge"],
            "input": {
                "subject": "Offert",
                "message_text": "Hej",
                "sender": {"name": "Anna", "email": "a@example.com"},
                "actions": [{"type": "notify_unknown_integration", "to": "x@example.com"}],
            },
            "tenant": {"auto_actions": {"lead": "full_auto"}},
            "ai": {"mode": "fixture_ai", "fixtures": {}},
            "pipeline": {
                "pre_seed": [
                    {
                        "processor": "policy_processor",
                        "result": {
                            "payload": {
                                "decision": "auto_execute",
                                "policy_authorization": "execution_allowed",
                                "detected_job_type": "lead",
                            }
                        },
                    }
                ],
                "steps": [{"run": "dispatch"}],
            },
            "expect": {
                "actions": {"notify_unknown_integration": {"absent": True}},
                "safety": {"real_external_calls": 0},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S19_invoice_no_dispatch",
            "category": "invoice",
            "tags": ["safety"],
            "input": {
                "subject": "Faktura INV-1001",
                "message_text": "Bifogad faktura på 12 500 kr.",
                "sender": {"name": "Leverantör", "email": "lev@example.com"},
            },
            "tenant": {
                "auto_actions": {"invoice": "full_auto"},
                "enabled_job_types": ["intake", "invoice"],
            },
            "ai": {"mode": "fixture_ai", "fixtures": INVOICE_FIXTURES},
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "classification": {"job_type": {"exact": "invoice"}},
                "safety": {"real_external_calls": 0, "telemetry": {"fake_adapter_calls": {"max": 0}}},
            },
        }
    )

    scenarios.append(
        {
            "schema_version": "2d.1",
            "scenario_id": "S20_data_deletion_request",
            "category": "data_protection",
            "tags": ["safety"],
            "input": {
                "subject": "Radera mina uppgifter",
                "message_text": "Jag begär radering av alla mina personuppgifter enligt GDPR.",
                "sender": {"name": "Erik Johansson", "email": "erik@example.com"},
            },
            "tenant": {"auto_actions": {}},
            "ai": {
                "mode": "fixture_ai",
                "fixtures": {
                    **INQUIRY_FIXTURES,
                    "classification_v1": {
                        "detected_job_type": "customer_inquiry",
                        "confidence": 0.9,
                        "reasons": ["gdpr"],
                    },
                },
            },
            "pipeline": {"steps": [{"run": "pipeline"}]},
            "expect": {
                "policy": {"authorization": {"one_of": ["hold_for_review", "approval_required"]}},
                "safety": {"real_external_calls": 0},
            },
        }
    )

    for scenario in scenarios:
        write_scenario(scenario)
    print(f"wrote {len(scenarios)} scenarios to {ROOT}")


if __name__ == "__main__":
    main()
