"""Evaluation context and production-path adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.customer.api_schemas import (
    CreateCompanyEndCustomerRequest,
    CreatePrivateEndCustomerRequest,
    OperatorAddFactRequest,
    OperatorCreateCustomerRequest,
    OperatorCreateIdentityRequest,
    OperatorCreateJobLinkRequest,
    OperatorUpdateCustomerRequest,
    OperatorVerifyFactRequest,
)
from app.domain.customer.enums import (
    CustomerType,
    EntityOwnerType,
    FactState,
    IdentityType,
    LinkType,
    SourceType,
    VerificationStatus,
)
from app.domain.customer.matching import assess_customer_match
from app.domain.customer.schemas import (
    CustomerMatchInput,
    CustomerMatchSubject,
    IdentityMatchItem,
)
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_command_service import EndCustomerCommandService
from app.services.end_customer_read_service import EndCustomerReadService

OperatorIdentity = dict[str, str]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


@dataclass
class EvalContext:
    engine: Engine
    tenant_id: str
    operator: OperatorIdentity = field(
        default_factory=lambda: {
            "id": "eval-operator",
            "display_name": "Eval Operator",
            "role": "admin",
        }
    )
    arrangements: list[str] = field(default_factory=list)
    production_actions: list[str] = field(default_factory=list)

    def session(self) -> Session:
        return sessionmaker(bind=self.engine)()

    def act_create_private_customer(
        self,
        db: Session,
        *,
        display_name: str = "Eval Private",
        email: str | None = None,
        phone: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.create_customer.private")
        request = OperatorCreateCustomerRequest(
            customer_type=CustomerType.PRIVATE,
            private=CreatePrivateEndCustomerRequest(
                display_name=display_name,
                email=email,
                phone=phone,
            ),
            reason="Stateful evaluation",
        )
        status, body = EndCustomerCommandService.create_customer(
            db, self.tenant_id, self.operator, request, idempotency_key
        )
        db.commit()
        return {"status": status, "body": body}

    def act_create_company_customer(
        self,
        db: Session,
        *,
        display_name: str,
        legal_name: str,
        contact_email: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.create_customer.company")
        request = OperatorCreateCustomerRequest(
            customer_type=CustomerType.COMPANY,
            company=CreateCompanyEndCustomerRequest(
                company_legal_name=legal_name,
                company_display_name=display_name,
                primary_contact_display_name="Primary Contact",
                primary_contact_email=contact_email,
            ),
            reason="Stateful evaluation",
        )
        status, body = EndCustomerCommandService.create_customer(
            db, self.tenant_id, self.operator, request, idempotency_key
        )
        db.commit()
        return {"status": status, "body": body}

    def act_add_fact(
        self,
        db: Session,
        customer_id: str,
        request: OperatorAddFactRequest,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.add_fact")
        status, body = EndCustomerCommandService.add_fact(
            db, self.tenant_id, customer_id, self.operator, request, idempotency_key
        )
        db.commit()
        return {"status": status, "body": body}

    def act_verify_fact(
        self,
        db: Session,
        customer_id: str,
        fact_id: str,
        verified_value: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.verify_fact")
        request = OperatorVerifyFactRequest(
            verified_raw_value=verified_value,
            normalized_value=verified_value,
            reason="Stateful evaluation verify",
        )
        status, body = EndCustomerCommandService.verify_fact(
            db,
            self.tenant_id,
            customer_id,
            fact_id,
            self.operator,
            request,
            idempotency_key,
        )
        db.commit()
        return {"status": status, "body": body}

    def act_create_identity(
        self,
        db: Session,
        customer_id: str,
        request: OperatorCreateIdentityRequest,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.create_identity")
        status, body = EndCustomerCommandService.create_identity(
            db, self.tenant_id, customer_id, self.operator, request, idempotency_key
        )
        db.commit()
        return {"status": status, "body": body}

    def act_create_job_link(
        self,
        db: Session,
        customer_id: str,
        job_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.create_job_link")
        request = OperatorCreateJobLinkRequest(
            job_id=job_id,
            link_type=LinkType.MANUAL,
            reason="Stateful evaluation",
        )
        status, body = EndCustomerCommandService.create_job_link(
            db, self.tenant_id, customer_id, self.operator, request, idempotency_key
        )
        db.commit()
        return {"status": status, "body": body}

    def act_update_customer(
        self,
        db: Session,
        customer_id: str,
        request: OperatorUpdateCustomerRequest,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.update_customer")
        status, body = EndCustomerCommandService.update_customer(
            db, self.tenant_id, customer_id, self.operator, request, idempotency_key
        )
        db.commit()
        return {"status": status, "body": body}

    def act_duplicate_decision(
        self,
        db: Session,
        candidate_id: str,
        decision: str,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.production_actions.append("command.duplicate_decision")
        status, body = EndCustomerCommandService.duplicate_decision(
            db,
            self.tenant_id,
            candidate_id,
            self.operator,
            decision,
            expected_version,
            "Stateful evaluation decision",
            idempotency_key,
        )
        db.commit()
        return {"status": status, "body": body}

    def read_customer_card(self, db: Session, customer_id: str) -> Any:
        self.production_actions.append("read.get_customer_card")
        return EndCustomerReadService.get_customer_card(db, self.tenant_id, customer_id)

    def assess_match(
        self,
        left: CustomerMatchSubject,
        right: CustomerMatchSubject,
    ) -> Any:
        self.production_actions.append("domain.assess_customer_match")
        return assess_customer_match(CustomerMatchInput(left=left, right=right))

    def arrange_contact(
        self,
        db: Session,
        display_name: str,
    ) -> str:
        self.arrangements.append("repository.create_contact")
        contact = EndCustomerRepository.create_contact(db, self.tenant_id, display_name=display_name)
        db.commit()
        return contact.contact_id

    def arrange_relationship(
        self,
        db: Session,
        customer_id: str,
        subject_type: EntityOwnerType,
        subject_id: str,
        relationship_type: str,
        is_primary: bool = False,
    ) -> None:
        self.arrangements.append("repository.create_relationship")
        from app.domain.customer.enums import RelationshipType

        EndCustomerRepository.create_relationship(
            db,
            self.tenant_id,
            customer_id,
            subject_type,
            subject_id,
            RelationshipType(relationship_type),
            is_primary=is_primary,
        )
        db.commit()

    def arrange_thread_link(
        self,
        db: Session,
        customer_id: str,
        thread_id: str,
    ) -> str:
        self.arrangements.append("repository.create_thread_link")
        link, _ = EndCustomerRepository.create_thread_link(
            db,
            self.tenant_id,
            customer_id,
            "gmail",
            "eval-account",
            thread_id,
            LinkType.MANUAL,
            1.0,
            SourceType.SYSTEM_DERIVED,
        )
        db.commit()
        return link.link_id

    def arrange_duplicate_candidate(
        self,
        db: Session,
        left_customer_id: str,
        right_customer_id: str,
    ) -> str:
        self.arrangements.append("repository.create_duplicate_candidate")
        candidate, _ = EndCustomerRepository.create_duplicate_candidate(
            db,
            self.tenant_id,
            left_customer_id,
            right_customer_id,
            0.85,
        )
        db.commit()
        return candidate.candidate_id

    def arrange_job(self, db: Session, job_id: str | None = None) -> str:
        self.arrangements.append("repository.create_job")
        from app.repositories.postgres.job_models import JobRecord

        job_id = job_id or new_id()
        now = utcnow()
        db.add(
            JobRecord(
                job_id=job_id,
                tenant_id=self.tenant_id,
                job_type="lead",
                status="pending",
                input_data={},
                result={},
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        return job_id

    def build_match_subject(
        self,
        subject_id: str,
        owner_type: EntityOwnerType,
        email: str | None = None,
        thread_id: str | None = None,
    ) -> CustomerMatchSubject:
        identities: list[IdentityMatchItem] = []
        if email:
            identities.append(
                IdentityMatchItem(
                    identity_type=IdentityType.EMAIL,
                    raw_value=email,
                    normalized_value=email.lower(),
                    verification_status=VerificationStatus.VERIFIED,
                    source_type=SourceType.GMAIL_INBOUND,
                )
            )
        return CustomerMatchSubject(
            tenant_id=self.tenant_id,
            subject_id=subject_id,
            owner_type=owner_type,
            identities=identities,
            gmail_thread_id=thread_id,
        )
