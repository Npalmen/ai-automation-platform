# app/integrations/retry_worker.py

import asyncio
from sqlalchemy.orm import Session

from app.repositories.postgres.session import SessionLocal
from app.domain.integrations.models import IntegrationEvent
from app.integrations.dispatcher import IntegrationDispatcher

POLL_INTERVAL = 10
MAX_BATCH = 20


async def run_worker():
    while True:
        db: Session = SessionLocal()

        try:
            events = (
                db.query(IntegrationEvent)
                .filter(IntegrationEvent.status == "failed")
                .order_by(IntegrationEvent.created_at.asc())
                .limit(MAX_BATCH)
                .all()
            )

            if events:
                dispatcher = IntegrationDispatcher(db)

                for event in events:
                    await dispatcher._execute(event)

        finally:
            db.close()

        await asyncio.sleep(POLL_INTERVAL)