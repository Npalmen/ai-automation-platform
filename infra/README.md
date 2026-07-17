# infra/

Infrastructure configuration for Krowolf. `docker-compose.prod.yml` mounts `./infra/Caddyfile` into the `caddy` service.

## Caddyfile status (Kapitel 0B, 2026-07-17)

- **No Caddy configuration existed in this git repository before this chapter.** `docker-compose.prod.yml` has referenced `./infra/Caddyfile` since it was written, but the file itself was never committed (`git log --all -- infra/ Caddyfile` returns no history).
- The real production Caddy configuration is understood to exist only on the production server (`/opt/krowolf/infra/Caddyfile`, per `docs/01-current-truth.md`). **It was NOT retrieved in Kapitel 0B.** This session had no SSH host/credentials configured, and prior sessions already documented SSH authentication failures against the production host (`docs/01-current-truth.md`, "Post-push deploy / Phase A-C re-run attempt (2026-07-07 20:24)" — `ssh` resolved to the `niklas` user but failed with permission denied).
- `Caddyfile.example` in this directory is a **hand-written target/example configuration**, not a copy of the live production file. It is inferred from:
  - `docker-compose.prod.yml` (Caddy proxies to the `app` service on port 8000; ports 80/443 published only on the `caddy` service).
  - `docs/10-live-verification-plan.md` and `docs/01-current-truth.md` (confirms `api.krowolf.se` and `app.krowolf.se` both resolve to the same production server and both currently reach the same FastAPI app; `admin.krowolf.se` is also treated as a UI host in `app/main.py`).
- **`Caddyfile.example` must not be treated as verified production truth.** It is a documented starting point for Kapitel 1C, not a deploy artifact.

## What must happen before a production deploy of the new operator panel

1. Retrieve the real `/opt/krowolf/infra/Caddyfile` **read-only** via SSH (requires valid production credentials, not available in this session).
2. Diff it against `Caddyfile.example` in this directory.
3. Commit the real file (with any secrets/certs stripped — Caddy config for this stack should not contain secrets, but verify) as `infra/Caddyfile`, reconciling with or replacing the example.
4. Do not reload/restart the production Caddy container as part of that retrieval — read-only inspection only.

This is tracked as a **deploy blocker**, not a Kapitel 1A blocker. See the DEC-024 deploy readiness matrix in `docs/07-decisions.md`.

## Shared status metadata (Kapitel 8)

Backup and restore scripts write machine-readable JSON under the shared `storage/status/` directory:

| File | Env var | Host path (cron/scripts) | Container path (FastAPI) |
|------|---------|--------------------------|--------------------------|
| Backup status | `BACKUP_STATUS_FILE` | `/opt/krowolf/storage/status/backup_status.json` | `/app/storage/status/backup_status.json` |
| Restore status | `RESTORE_STATUS_FILE` | `/opt/krowolf/storage/status/restore_status.json` | `/app/storage/status/restore_status.json` |

Both resolve to the same files via `docker-compose.prod.yml` bind mount `./storage:/app/storage`.

**One-time server setup:** ensure `storage/status/` exists with mode `0750`, files `0640`, and group-readable by the app container user (see `docs/runbooks/backup-and-restore.md`).

Build identity is baked into the image at `/app/build-metadata.json` via `scripts/write_build_metadata.py` during Docker build (not from git at runtime).
