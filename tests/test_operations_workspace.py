from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _record(input_data: dict | None = None):
    r = MagicMock()
    r.job_id = "JOB-OPS-1"
    r.tenant_id = "TENANT_1"
    r.input_data = input_data or {}
    return r


def _db_with_record(record):
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = record
    return db


def test_get_operations_workspace_returns_defaults_when_missing():
    from app.main import get_case_operations_workspace

    db = _db_with_record(_record())
    out = get_case_operations_workspace(job_id="JOB-OPS-1", db=db, tenant_id="TENANT_1")
    ws = out["workspace"]

    assert out["job_id"] == "JOB-OPS-1"
    assert ws["work_order"]["status"] == "new"
    assert ws["project"]["status"] == "intake"
    assert ws["delivery_package"]["status"] == "not_started"
    assert ws["checklists"]["site_survey"][0]["id"] == "access_confirmed"


def test_put_operations_workspace_merges_nested_fields_without_dropping_existing():
    from app.main import put_case_operations_workspace, OperationsWorkspaceUpdateRequest

    existing = {
        "operations_workspace": {
            "project": {"name": "Villa Sol", "status": "planning"},
            "work_order": {"technician": "Alex", "status": "planned"},
        }
    }
    db = _db_with_record(_record(input_data=existing))
    body = OperationsWorkspaceUpdateRequest(workspace={"project": {"status": "active"}})

    out = put_case_operations_workspace(job_id="JOB-OPS-1", body=body, db=db, tenant_id="TENANT_1")
    ws = out["workspace"]

    assert ws["project"]["status"] == "active"
    assert ws["project"]["name"] == "Villa Sol"
    assert ws["work_order"]["technician"] == "Alex"
    assert db.commit.called


def test_put_operations_workspace_rejects_invalid_work_order_status():
    from app.main import put_case_operations_workspace, OperationsWorkspaceUpdateRequest

    db = _db_with_record(_record())
    body = OperationsWorkspaceUpdateRequest(workspace={"work_order": {"status": "broken_status"}})

    with pytest.raises(HTTPException) as exc:
        put_case_operations_workspace(job_id="JOB-OPS-1", body=body, db=db, tenant_id="TENANT_1")
    assert exc.value.status_code == 422
    assert "work_order.status" in str(exc.value.detail)


def test_add_operations_timeline_appends_event():
    from app.main import add_case_operations_timeline_event, OperationsTimelineEventRequest

    db = _db_with_record(_record())
    body = OperationsTimelineEventRequest(message="Tekniker bokad", event_type="scheduling")
    out = add_case_operations_timeline_event(job_id="JOB-OPS-1", body=body, db=db, tenant_id="TENANT_1")

    assert out["status"] == "ok"
    assert out["timeline_count"] == 1
    saved_ws = db.query.return_value.filter.return_value.first.return_value.input_data["operations_workspace"]
    assert saved_ws["timeline"][0]["message"] == "Tekniker bokad"
    assert db.commit.called


def test_update_delivery_package_sent_sets_sent_timestamp():
    from app.main import update_case_delivery_package, DeliveryPackageUpdateRequest

    db = _db_with_record(_record())
    body = DeliveryPackageUpdateRequest(status="sent", recipient_email="kund@example.com")
    out = update_case_delivery_package(job_id="JOB-OPS-1", body=body, db=db, tenant_id="TENANT_1")

    delivery = out["delivery_package"]
    assert delivery["status"] == "sent"
    assert delivery["recipient_email"] == "kund@example.com"
    assert delivery["sent_at"] is not None


def test_apply_installer_checklist_template_replaces_with_project_specific_items():
    from app.main import (
        OperationsChecklistTemplateRequest,
        apply_case_operations_checklist_template,
    )

    db = _db_with_record(_record())
    body = OperationsChecklistTemplateRequest(installation_type="ev_charger", replace=True)

    out = apply_case_operations_checklist_template(
        job_id="JOB-OPS-1",
        body=body,
        db=db,
        tenant_id="TENANT_1",
    )

    assert out["installation_type"] == "ev_charger"
    assert out["checklists"]["site_survey"][0]["id"] == "parking_location_confirmed"
    saved_ws = db.query.return_value.filter.return_value.first.return_value.input_data["operations_workspace"]
    assert saved_ws["project"]["installation_type"] == "ev_charger"
    assert db.commit.called


def test_apply_installer_checklist_template_merges_without_dropping_completed_items():
    from app.main import (
        OperationsChecklistTemplateRequest,
        apply_case_operations_checklist_template,
    )

    existing = {
        "operations_workspace": {
            "checklists": {
                "site_survey": [
                    {
                        "id": "custom_item",
                        "label": "Egen kontrollpunkt",
                        "done": True,
                        "note": "klar",
                    }
                ],
            }
        }
    }
    db = _db_with_record(_record(input_data=existing))
    body = OperationsChecklistTemplateRequest(installation_type="solar")

    out = apply_case_operations_checklist_template(
        job_id="JOB-OPS-1",
        body=body,
        db=db,
        tenant_id="TENANT_1",
    )

    site_survey_ids = [item["id"] for item in out["checklists"]["site_survey"]]
    assert "custom_item" in site_survey_ids
    assert "roof_condition_checked" in site_survey_ids


def test_add_operations_documentation_adds_item_to_bucket():
    from app.main import (
        OperationsDocumentationCreateRequest,
        add_case_operations_documentation,
    )

    db = _db_with_record(_record())
    body = OperationsDocumentationCreateRequest(
        bucket="before_images",
        name="Före installation",
        url="https://example.com/before.jpg",
        note="Bild från uppstart",
    )

    out = add_case_operations_documentation(job_id="JOB-OPS-1", body=body, db=db, tenant_id="TENANT_1")

    assert out["bucket"] == "before_images"
    assert out["count"] == 1
    doc = out["documentation"]["before_images"][0]
    assert doc["name"] == "Före installation"
    assert doc["url"] == "https://example.com/before.jpg"
    assert doc["created_at"] is not None
    assert db.commit.called


def test_add_operations_documentation_rejects_unknown_bucket():
    from app.main import (
        OperationsDocumentationCreateRequest,
        add_case_operations_documentation,
    )

    db = _db_with_record(_record())
    body = OperationsDocumentationCreateRequest(bucket="random", name="Fel")

    with pytest.raises(HTTPException) as exc:
        add_case_operations_documentation(job_id="JOB-OPS-1", body=body, db=db, tenant_id="TENANT_1")
    assert exc.value.status_code == 422
    assert "Unknown documentation bucket" in str(exc.value.detail)
