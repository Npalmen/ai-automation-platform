# app/integrations/dispatcher.py

import asyncio
from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.integration_repository import IntegrationRepository

from app.integrations.crm.webhook_client import CRMWebhookClient
from app.integrations.accounting.webhook_client import AccountingWebhookClient
from app.integrations.support.webhook_client import SupportWebhookClient

from app.integrations.monday.adapter import MondayAdapter
from app.integrations.monday.mappers import (
    map_lead_to_monday_item,
    map_invoice_to_monday_item,
    map_inquiry_to_monday_item,
)

from app.integrations.fortnox.adapter import FortnoxAdapter
from app.integrations.fortnox.mappers import (
    map_invoice_to_fortnox_customer,
    map_invoice_to_fortnox_invoice,
)

from app.integrations.visma.adapter import VismaAdapter
from app.integrations.visma.mappers import (
    map_invoice_to_visma_customer,
    map_invoice_to_visma_invoice,
)

from app.integrations.enums import IntegrationType
from app.integrations.policies import is_integration_enabled_for_tenant
from app.integrations.service import get_integration_connection_config

from app.core.settings import get_settings


class IntegrationDispatcher:
    def __init__(self, db: Session):
        settings = get_settings()
        self.db = db
        self.repo = IntegrationRepository(db)

        self.crm = CRMWebhookClient(
            base_url=settings.CRM_WEBHOOK_URL,
            api_key=settings.CRM_API_KEY,
        )

        self.accounting = AccountingWebhookClient(
            base_url=settings.ACCOUNTING_WEBHOOK_URL,
            api_key=settings.ACCOUNTING_API_KEY,
        )

        self.support = SupportWebhookClient(
            base_url=settings.SUPPORT_WEBHOOK_URL,
            api_key=settings.SUPPORT_API_KEY,
        )

    async def dispatch(self, job: Job):
        tenant_id = job.tenant_id

        if job.job_type == "lead_processing":
            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.CRM):
                await self._handle(job, IntegrationType.CRM)

            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.MONDAY):
                await self._handle(job, IntegrationType.MONDAY)

        if job.job_type == "invoice_processing":
            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.ACCOUNTING):
                await self._handle(job, IntegrationType.ACCOUNTING)

            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.MONDAY):
                await self._handle(job, IntegrationType.MONDAY)

            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.FORTNOX):
                await self._handle(job, IntegrationType.FORTNOX)

            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.VISMA):
                await self._handle(job, IntegrationType.VISMA)

        if job.job_type == "inquiry_processing":
            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.SUPPORT):
                await self._handle(job, IntegrationType.SUPPORT)

            if is_integration_enabled_for_tenant(tenant_id, IntegrationType.MONDAY):
                await self._handle(job, IntegrationType.MONDAY)

    async def _handle(self, job: Job, integration_type: IntegrationType):
        payload = self._build_payload(job, integration_type)

        idempotency_key = f"{job.id}-{integration_type.value}"

        existing = self.repo.get_by_idempotency_key(idempotency_key)
        if existing:
            return

        event = IntegrationEvent(
            job_id=str(job.id),
            tenant_id=job.tenant_id,
            integration_type=integration_type.value,
            payload=payload,
            idempotency_key=idempotency_key,
        )

        self.repo.create(event)

        await self._execute(event)

    async def _execute(self, event: IntegrationEvent):
        if event.status == "dead":
            return

        try:
            event.attempts += 1

            await asyncio.sleep(min(event.attempts * 2, 30))

            if event.integration_type == "crm":
                response = await self.crm.send(
                    payload=event.payload,
                    idempotency_key=event.idempotency_key,
                )

            elif event.integration_type == "accounting":
                response = await self.accounting.send(
                    payload=event.payload,
                    idempotency_key=event.idempotency_key,
                )

            elif event.integration_type == "support":
                response = await self.support.send(
                    payload=event.payload,
                    idempotency_key=event.idempotency_key,
                )

            elif event.integration_type == "monday":
                connection_config = get_integration_connection_config(
                    event.tenant_id,
                    IntegrationType.MONDAY,
                )

                adapter = MondayAdapter(connection_config=connection_config)

                mapped_payload = self._map_monday_payload(event.payload)

                response = adapter.execute_action(
                    action="create_item",
                    payload=mapped_payload,
                )

            elif event.integration_type == "fortnox":
                connection_config = get_integration_connection_config(
                    event.tenant_id,
                    IntegrationType.FORTNOX,
                )

                adapter = FortnoxAdapter(connection_config=connection_config)

                mapped_payload = self._map_fortnox_payload(event.payload)

                adapter.execute_action(
                    action="create_customer",
                    payload={"customer": mapped_payload["customer"]},
                )

                response = adapter.execute_action(
                    action="create_invoice",
                    payload={"invoice": mapped_payload["invoice"]},
                )

            elif event.integration_type == "visma":
                connection_config = get_integration_connection_config(
                    event.tenant_id,
                    IntegrationType.VISMA,
                )

                adapter = VismaAdapter(connection_config=connection_config)

                mapped_payload = self._map_visma_payload(event.payload)

                adapter.execute_action(
                    action="create_customer",
                    payload={"customer": mapped_payload["customer"]},
                )

                response = adapter.execute_action(
                    action="create_invoice",
                    payload={"invoice": mapped_payload["invoice"]},
                )

            else:
                response = None

            if response:
                event.status = "success"
                event.last_error = None
            else:
                raise Exception("No response from integration")

        except Exception as e:
            event.last_error = str(e)

            if event.attempts >= 3:
                event.status = "dead"
            else:
                event.status = "failed"

        finally:
            self.repo.update(event)

    def _map_monday_payload(self, payload: dict):
        job_type = payload.get("type")

        if job_type == "lead_processing":
            return map_lead_to_monday_item(payload)

        if job_type == "invoice_processing":
            return map_invoice_to_monday_item(payload)

        if job_type == "inquiry_processing":
            return map_inquiry_to_monday_item(payload)

        return {
            "item_name": "Unknown",
            "column_values": {},
        }

    def _map_fortnox_payload(self, payload: dict):
        return {
            "customer": map_invoice_to_fortnox_customer(payload),
            "invoice": map_invoice_to_fortnox_invoice(payload),
        }

    def _map_visma_payload(self, payload: dict):
        return {
            "customer": map_invoice_to_visma_customer(payload),
            "invoice": map_invoice_to_visma_invoice(payload),
        }

    def _build_payload(self, job: Job, integration_type: IntegrationType):
        history = job.processor_history or []

        def get(name):
            for h in reversed(history):
                if h["processor"] == name:
                    return h["result"]
            return None

        return {
            "job_id": str(job.id),
            "type": job.job_type,
            "integration": integration_type.value,
            "data": job.input_data,
            "classification": get("classification"),
            "scoring": get("lead_scoring"),
            "validation": get("invoice_validation"),
        }