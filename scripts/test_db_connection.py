from sqlalchemy import text

from app.repositories.postgres.database import engine


def main():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("DB OK:", result.scalar())


if __name__ == "__main__":
    main()