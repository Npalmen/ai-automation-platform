from app.repositories.postgres.database import Base, engine
from app.repositories.postgres import job_models  # noqa: F401
from app.repositories.postgres import audit_models  # noqa: F401
from app.repositories.postgres import approval_models  # noqa: F401
from app.repositories.postgres import action_execution_models  # noqa: F401


def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created:", list(Base.metadata.tables.keys()))


if __name__ == "__main__":
    main()