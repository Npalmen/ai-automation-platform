#!/usr/bin/env python3
"""One-time Visma OAuth credential migration: local DB -> production DB.

Does not print access_token, refresh_token, or client secrets.
Does not modify tenant allowed_integrations or perform Visma writes.

Transport: secure local payload file (chmod 600) -> scp -> docker exec import -> delete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.audit_service import create_audit_event
from app.core.settings import Settings, get_settings
from app.integrations.visma.oauth_service import refresh_access_token, test_connection
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

TENANT_ID = "T_NIKLAS_DEMO_001"
PROVIDER = "visma"
REMOTE_HOST = "ubuntu@api.krowolf.se"
REMOTE_APP_CONTAINER = "krowolf-app-1"
TEMP_DIR = Path(__file__).resolve().parent / ".tmp" / "visma_oauth_migration"

SECRET_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "client_secret",
        "client_id",
        "authorization",
    }
)


class MigrationError(Exception):
    """Raised when migration preconditions fail."""


def fingerprint_secret(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def assert_tenant_id(tenant_id: str) -> None:
    if tenant_id != TENANT_ID:
        raise MigrationError(f"Source tenant must be {TENANT_ID}, got {tenant_id!r}")


def load_source_credential(db: Session, tenant_id: str = TENANT_ID) -> OAuthCredentialRecord:
    assert_tenant_id(tenant_id)
    record = OAuthCredentialRepository.get(db, tenant_id, PROVIDER)
    if record is None:
        raise MigrationError(f"No local Visma credential for tenant {tenant_id}")
    if record.tenant_id != TENANT_ID:
        raise MigrationError(f"Credential tenant mismatch: expected {TENANT_ID}, got {record.tenant_id!r}")
    return record


def require_refresh_token(record: OAuthCredentialRecord) -> None:
    if not (record.refresh_token or "").strip():
        raise MigrationError(f"Visma credential for {record.tenant_id} is missing refresh_token")


def client_ids_match(local_settings: Settings, remote_fingerprint: str) -> bool:
    local_fp = fingerprint_secret(local_settings.VISMA_CLIENT_ID)
    return bool(local_fp) and local_fp == (remote_fingerprint or "").strip()


def refresh_source_credential(record: OAuthCredentialRecord) -> dict[str, Any]:
    require_refresh_token(record)
    try:
        return refresh_access_token(record.refresh_token)
    except Exception as exc:
        raise MigrationError(f"Visma refresh failed: {type(exc).__name__}") from exc


def optional_company_test(access_token: str) -> dict[str, Any]:
    try:
        company = test_connection(access_token)
    except Exception as exc:
        return {
            "company_test_ok": False,
            "error_type": type(exc).__name__,
        }
    name = company.get("Name") or company.get("name")
    return {
        "company_test_ok": True,
        "has_company_name": bool(name),
    }


def merge_migration_metadata(source_metadata: dict | None) -> dict[str, Any]:
    base = dict(source_metadata or {})
    base["connected_via"] = "oauth_credential_migration"
    base["source_environment"] = "local"
    base["migrated_at"] = datetime.now(timezone.utc).isoformat()
    return base


def build_migration_payload(
    record: OAuthCredentialRecord,
    refreshed: dict[str, Any],
    *,
    local_settings: Settings,
    company_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert_tenant_id(record.tenant_id)
    expires_at = refreshed.get("expires_at")
    expires_at_str = expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at

    source_meta = dict(record.metadata_json or {})
    token_type = source_meta.pop("token_type", None)

    metadata_json = merge_migration_metadata(source_meta)
    if token_type:
        metadata_json["token_type"] = token_type

    payload: dict[str, Any] = {
        "version": 1,
        "tenant_id": TENANT_ID,
        "provider": PROVIDER,
        "access_token": refreshed["access_token"],
        "refresh_token": refreshed.get("refresh_token") or record.refresh_token,
        "expires_at": expires_at_str,
        "scopes": refreshed.get("scopes") or record.scopes,
        "metadata_json": metadata_json,
        "client_id_fingerprint": fingerprint_secret(local_settings.VISMA_CLIENT_ID),
        "validation": {
            "refresh_ok": True,
            "tenant_id": TENANT_ID,
        },
    }
    if company_validation is not None:
        payload["validation"]["company"] = company_validation
    return payload


def redact_for_output(data: Any) -> Any:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key in SECRET_KEYS:
                out[key] = "<redacted>"
            else:
                out[key] = redact_for_output(value)
        return out
    if isinstance(data, list):
        return [redact_for_output(item) for item in data]
    return data


def ensure_no_secrets_in_text(text: str, secrets: list[str]) -> None:
    for secret in secrets:
        if secret and secret in text:
            raise MigrationError("Refusing to emit output that contains secret values")


def safe_json_dumps(data: Any, *, secrets: list[str] | None = None) -> str:
    redacted = redact_for_output(data)
    rendered = json.dumps(redacted, indent=2, default=str)
    if secrets:
        ensure_no_secrets_in_text(rendered, [s for s in secrets if s])
    return rendered


def write_secure_payload(payload: dict[str, Any]) -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMP_DIR / f"visma_oauth_migration_{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def read_secure_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MigrationError(f"Payload file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def delete_secure_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def get_tenant_integration_snapshot(db: Session, tenant_id: str) -> dict[str, Any]:
    config = TenantConfigRepository.get(db, tenant_id)
    if config is None:
        return {"found": False}
    return {
        "found": True,
        "allowed_integrations": list(config.allowed_integrations or []),
        "auto_actions": dict(config.auto_actions or {}),
    }


def production_credential_exists(db: Session, tenant_id: str = TENANT_ID) -> bool:
    return OAuthCredentialRepository.get(db, tenant_id, PROVIDER) is not None


def apply_production_import(
    db: Session,
    payload: dict[str, Any],
    *,
    replace: bool,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    tenant_id = payload.get("tenant_id")
    assert_tenant_id(str(tenant_id))

    if payload.get("provider") != PROVIDER:
        raise MigrationError(f"Expected provider {PROVIDER!r}")

    remote_fp = str(payload.get("client_id_fingerprint") or "")
    if not remote_fp or fingerprint_secret(settings.VISMA_CLIENT_ID) != remote_fp:
        raise MigrationError("Production VISMA_CLIENT_ID does not match source fingerprint")

    if not (payload.get("refresh_token") or "").strip():
        raise MigrationError("Payload missing refresh_token")

    before_tenant = get_tenant_integration_snapshot(db, TENANT_ID)
    exists = production_credential_exists(db, TENANT_ID)
    if exists and not replace:
        raise MigrationError(
            f"Production already has Visma credential for {TENANT_ID}; pass --replace to overwrite"
        )

    OAuthCredentialRepository.upsert(
        db=db,
        tenant_id=TENANT_ID,
        provider=PROVIDER,
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=_parse_expires_at(payload.get("expires_at")),
        scopes=payload.get("scopes"),
        metadata_json=payload.get("metadata_json"),
    )

    create_audit_event(
        db=db,
        tenant_id=TENANT_ID,
        category="integration",
        action="visma_oauth_credential_migrated",
        status="success",
        details={
            "provider": PROVIDER,
            "replaced_existing": exists,
            "source_environment": "local",
            "validation": redact_for_output(payload.get("validation") or {}),
        },
    )

    after_tenant = get_tenant_integration_snapshot(db, TENANT_ID)
    if before_tenant != after_tenant:
        raise MigrationError("Tenant config changed during import; aborting as unsafe")

    return {
        "status": "imported",
        "tenant_id": TENANT_ID,
        "provider": PROVIDER,
        "replaced_existing": exists,
        "tenant_config_unchanged": True,
    }


def _parse_expires_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    raise MigrationError("Invalid expires_at in payload")


def run_local_validation(
    db: Session,
    *,
    local_settings: Settings,
    remote_client_fingerprint: str | None = None,
    run_company_test: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = load_source_credential(db, TENANT_ID)
    require_refresh_token(record)

    if remote_client_fingerprint is not None:
        if not client_ids_match(local_settings, remote_client_fingerprint):
            raise MigrationError("Local and production VISMA_CLIENT_ID do not match")

    refreshed = refresh_source_credential(record)
    company_validation = optional_company_test(refreshed["access_token"]) if run_company_test else None
    if company_validation and not company_validation.get("company_test_ok"):
        raise MigrationError("Visma companysettings read validation failed")

    payload = build_migration_payload(
        record,
        refreshed,
        local_settings=local_settings,
        company_validation=company_validation,
    )

    report = {
        "status": "validated",
        "tenant_id": TENANT_ID,
        "provider": PROVIDER,
        "has_refresh_token": True,
        "client_id_match": True if remote_client_fingerprint is None else client_ids_match(
            local_settings, remote_client_fingerprint
        ),
        "refresh_ok": True,
        "company_test": company_validation,
        "expires_at": payload.get("expires_at"),
        "scopes": payload.get("scopes"),
    }
    return report, payload


def fetch_remote_client_fingerprint() -> str:
    code = (
        "import json\n"
        "from app.core.settings import get_settings\n"
        "import hashlib\n"
        "v = (get_settings().VISMA_CLIENT_ID or '').strip()\n"
        "fp = hashlib.sha256(v.encode()).hexdigest() if v else ''\n"
        "print(json.dumps({'client_id_fingerprint': fp, 'configured': bool(v)}))\n"
    )
    result = _docker_python(code)
    if not result.get("ok"):
        raise MigrationError(f"Failed to read production client fingerprint: {result.get('stderr', 'unknown')}")
    if not result.get("configured"):
        raise MigrationError("Production VISMA_CLIENT_ID is not configured")
    return str(result.get("client_id_fingerprint") or "")


def remote_production_credential_exists() -> bool:
    code = f"""
import json
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
db = SessionLocal()
try:
    rec = OAuthCredentialRepository.get(db, "{TENANT_ID}", "{PROVIDER}")
    print(json.dumps({{"exists": rec is not None}}))
finally:
    db.close()
"""
    result = _docker_python(code)
    if not result.get("ok"):
        raise MigrationError(f"Failed to check production credential: {result.get('stderr', 'unknown')}")
    return bool(result.get("exists"))


def _docker_python(code: str) -> dict[str, Any]:
    """Run Python in the production app container via SSH stdin (Windows-safe quoting)."""
    remote_cmd = f"sudo docker exec -i {REMOTE_APP_CONTAINER} python -"
    proc = subprocess.run(
        ["ssh", REMOTE_HOST, remote_cmd],
        input=code,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        return {"ok": False, "stderr": (proc.stderr or proc.stdout)[:500]}
    try:
        return {"ok": True, **json.loads((proc.stdout or "").strip())}
    except json.JSONDecodeError:
        return {"ok": False, "stderr": (proc.stdout or proc.stderr)[:500]}


def _scp_to_remote(local_path: Path, remote_path: str) -> None:
    proc = subprocess.run(
        ["scp", str(local_path), f"{REMOTE_HOST}:{remote_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise MigrationError(f"scp failed: {(proc.stderr or proc.stdout)[:300]}")


def _docker_cp_host_to_container(host_path: str, container_path: str) -> None:
    proc = subprocess.run(
        [
            "ssh",
            REMOTE_HOST,
            f"sudo docker cp {host_path} {REMOTE_APP_CONTAINER}:{container_path}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise MigrationError(
            f"docker cp failed: {(proc.stderr or proc.stdout)[:300]}"
        )


def _scp_script_to_remote(local_path: Path, remote_path: str) -> None:
    _scp_to_remote(local_path, remote_path)


def _ssh_remote_import(remote_payload_host: str, remote_payload_container: str, replace: bool) -> dict[str, Any]:
    remote_script_host = "/tmp/migrate_visma_oauth_credential.py"
    remote_script_container = "/tmp/migrate_visma_oauth_credential.py"
    replace_flag = " --replace" if replace else ""

    _docker_cp_host_to_container(remote_script_host, remote_script_container)
    _docker_cp_host_to_container(remote_payload_host, remote_payload_container)

    remote_cmd = (
        f"sudo docker exec {REMOTE_APP_CONTAINER} python {remote_script_container} "
        f"--remote-import --payload {remote_payload_container}{replace_flag}"
    )
    proc = subprocess.run(
        ["ssh", REMOTE_HOST, remote_cmd],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout)[:500]
        raise MigrationError(f"Remote import failed: {detail}")
    try:
        return json.loads((proc.stdout or "").strip())
    except json.JSONDecodeError as exc:
        raise MigrationError("Remote import returned non-JSON output") from exc


def _ssh_delete_remote(host_path: str, container_path: str | None = None) -> None:
    subprocess.run(
        ["ssh", REMOTE_HOST, f"rm -f {host_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if container_path:
        subprocess.run(
            [
                "ssh",
                REMOTE_HOST,
                f"sudo docker exec {REMOTE_APP_CONTAINER} rm -f {container_path}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )


def run_remote_import_cli(payload_path: Path, *, replace: bool) -> dict[str, Any]:
    payload = read_secure_payload(payload_path)
    db = SessionLocal()
    try:
        result = apply_production_import(db, payload, replace=replace)
    finally:
        db.close()
    delete_secure_file(payload_path)
    return result


def run_migrate(*, replace: bool, run_company_test: bool = True) -> dict[str, Any]:
    local_settings = get_settings()
    if not (local_settings.VISMA_CLIENT_ID or "").strip():
        raise MigrationError("Local VISMA_CLIENT_ID is not configured")
    if not (local_settings.VISMA_CLIENT_SECRET or "").strip():
        raise MigrationError("Local VISMA_CLIENT_SECRET is not configured")

    remote_fp = fetch_remote_client_fingerprint()
    if remote_production_credential_exists() and not replace:
        raise MigrationError(
            f"Production already has Visma credential for {TENANT_ID}; pass --replace to overwrite"
        )

    db = SessionLocal()
    local_payload_path: Path | None = None
    remote_payload_host: str | None = None
    remote_payload_container = "/tmp/visma_oauth_migration_payload.json"
    remote_script_host = "/tmp/migrate_visma_oauth_credential.py"
    remote_script_container = "/tmp/migrate_visma_oauth_credential.py"
    secrets: list[str] = []
    try:
        report, payload = run_local_validation(
            db,
            local_settings=local_settings,
            remote_client_fingerprint=remote_fp,
            run_company_test=run_company_test,
        )
        secrets = [payload.get("access_token", ""), payload.get("refresh_token", "")]
        local_payload_path = write_secure_payload(payload)
        remote_payload_host = f"/tmp/{local_payload_path.name}"

        _scp_script_to_remote(Path(__file__).resolve(), remote_script_host)
        _scp_to_remote(local_payload_path, remote_payload_host)
        os.chmod(local_payload_path, 0o600)

        import_result = _ssh_remote_import(
            remote_payload_host,
            remote_payload_container,
            replace,
        )
        _ssh_delete_remote(remote_script_host, remote_script_container)
        _ssh_delete_remote(remote_payload_host, remote_payload_container)

        combined = {
            "status": "migrated",
            "validation": report,
            "import": import_result,
        }
        return combined
    finally:
        db.close()
        if local_payload_path is not None:
            delete_secure_file(local_payload_path)
        if remote_payload_host is not None:
            _ssh_delete_remote(remote_payload_host, remote_payload_container)
        _ssh_delete_remote(remote_script_host, remote_script_container)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate Visma OAuth credential local -> production")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate local credential and refresh; do not write to production",
    )
    parser.add_argument(
        "--check-production",
        action="store_true",
        help="Report whether production already has a Visma credential",
    )
    parser.add_argument(
        "--remote-import",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--payload", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite existing production Visma credential for T_NIKLAS_DEMO_001",
    )
    parser.add_argument(
        "--skip-company-test",
        action="store_true",
        help="Skip companysettings read validation during local refresh check",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.remote_import:
            if not args.payload:
                raise MigrationError("--remote-import requires --payload")
            result = run_remote_import_cli(args.payload, replace=args.replace)
        elif args.check_production:
            result = {
                "tenant_id": TENANT_ID,
                "provider": PROVIDER,
                "production_credential_exists": remote_production_credential_exists(),
                "production_client_configured": bool(fetch_remote_client_fingerprint()),
            }
        elif args.validate_only:
            local_settings = get_settings()
            remote_fp = fetch_remote_client_fingerprint()
            db = SessionLocal()
            try:
                result, _payload = run_local_validation(
                    db,
                    local_settings=local_settings,
                    remote_client_fingerprint=remote_fp,
                    run_company_test=not args.skip_company_test,
                )
            finally:
                db.close()
        else:
            result = run_migrate(replace=args.replace, run_company_test=not args.skip_company_test)

        secrets: list[str] = []
        if isinstance(result, dict):
            # Best-effort secret guard for nested validation paths
            for key in ("access_token", "refresh_token"):
                val = result.get(key)
                if isinstance(val, str):
                    secrets.append(val)

        print(safe_json_dumps(result, secrets=secrets))
        return 0
    except MigrationError as exc:
        print(safe_json_dumps({"status": "error", "error": str(exc)}))
        return 1
    except Exception as exc:
        print(safe_json_dumps({"status": "error", "error": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
