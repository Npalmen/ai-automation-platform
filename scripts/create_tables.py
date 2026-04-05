from app.repositories.postgres.database import Base, engine
from app.repositories.postgres import job_models
from app.repositories.postgres import audit_models


def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")


if __name__ == "__main__":
    main()