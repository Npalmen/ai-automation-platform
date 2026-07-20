"""One-shot helper to ensure ai_platform_eval exists (local sign-off only)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DATABASE_URL="):
        database_url = line.split("=", 1)[1].strip()
        break
else:
    raise SystemExit("DATABASE_URL missing from .env")

base = database_url.rsplit("/", 1)[0]
admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT", pool_pre_ping=True)
with admin.connect() as conn:
    exists = conn.execute(
        text("SELECT 1 FROM pg_database WHERE datname = 'ai_platform_eval'")
    ).scalar()
    if not exists:
        conn.execute(text("CREATE DATABASE ai_platform_eval"))
        print("created")
    else:
        print("exists")
    version = conn.execute(text("SELECT version()")).scalar()
    print(version.split(",")[0] if version else "unknown")
