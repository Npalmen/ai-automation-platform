# app/repositories/postgres/integration_repository.py

from sqlalchemy.orm import Session

from app.domain.integrations.models import IntegrationEvent


class IntegrationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, event: IntegrationEvent):
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def update(self, event: IntegrationEvent):
        self.db.commit()
        self.db.refresh(event)
        return event

    def get_by_idempotency_key(self, key: str):
        return (
            self.db.query(IntegrationEvent)
            .filter(IntegrationEvent.idempotency_key == key)
            .first()
        )

    def list_events_for_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        integration_type: str | None = None,
    ):
        query = self.db.query(IntegrationEvent).filter(
            IntegrationEvent.tenant_id == tenant_id
        )

        if status:
            query = query.filter(IntegrationEvent.status == status)

        if integration_type:
            query = query.filter(IntegrationEvent.integration_type == integration_type)

        return (
            query.order_by(IntegrationEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_events_for_tenant(
        self,
        tenant_id: str,
        status: str | None = None,
        integration_type: str | None = None,
    ):
        query = self.db.query(IntegrationEvent).filter(
            IntegrationEvent.tenant_id == tenant_id
        )

        if status:
            query = query.filter(IntegrationEvent.status == status)

        if integration_type:
            query = query.filter(IntegrationEvent.integration_type == integration_type)

        return query.count()

    def get_event_by_id(self, tenant_id: str, event_id: int):
        return (
            self.db.query(IntegrationEvent)
            .filter(
                IntegrationEvent.id == event_id,
                IntegrationEvent.tenant_id == tenant_id,
            )
            .first()
        )

    def list_all_events(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        integration_type: str | None = None,
    ):
        query = self.db.query(IntegrationEvent)

        if status:
            query = query.filter(IntegrationEvent.status == status)

        if integration_type:
            query = query.filter(IntegrationEvent.integration_type == integration_type)

        return (
            query.order_by(IntegrationEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_all_events(
        self,
        status: str | None = None,
        integration_type: str | None = None,
    ):
        query = self.db.query(IntegrationEvent)

        if status:
            query = query.filter(IntegrationEvent.status == status)

        if integration_type:
            query = query.filter(IntegrationEvent.integration_type == integration_type)

        return query.count()