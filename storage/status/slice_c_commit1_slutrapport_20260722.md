# Slice C Efterarbete — Commit 1 slutrapport
Generated: 2026-07-22T00:30Z (UTC)

## Git
| Item | Value |
|------|-------|
| Commit 1 SHA | `c1bc208` — fix: record canonical runtime commit in backfill audit |
| PR | https://github.com/Npalmen/ai-automation-platform/pull/8 |
| CI | Release Gate: tests ✅ frontend ✅ docker ✅ |
| Merge SHA | `967df7a181b7da43d9a45f2c9a01eff3aa920e62` |
| origin/main HEAD | `49ecc82` (docs-only + 2F.1 efter merge; ej deployad) |
| RUNTIME_CODE_SHA | `967df7a181b7da43d9a45f2c9a01eff3aa920e62` |
| Docs-only SHA (ej i image) | `49ecc82`, `122b469` |

## Image / deploy
| Item | Value |
|------|-------|
| Image tag | `krowolf-app:rc-967df7a181b7` |
| Digest | `sha256:8fe162e48a757f1bef85cf248100f1c8026df418dc1b8305b87c6d14b4e16605` |
| build-metadata.json | commit_sha=967df7a..., release_id=rc-967df7a181b7, build_time=2026-07-22T00:22:54Z |
| App start | 2026-07-22T00:23:23Z |
| /health | 200 ok |
| db/caddy | Oförändrade (endast app-container återskapad) |
| Pre-deploy backup | `/opt/krowolf/backups/pre-canonical-commit-20260722T002252Z.sql.gz` (gzip OK) |

## Backfill audit (pilot dry-run)
| Field | Value |
|-------|-------|
| audit row ID | `3fa356a6-1c10-4788-86ba-e691cac5bbbe` |
| status | completed |
| dry_run | true |
| tenant_data_changed | false |
| tenants_updated | 0 |
| actor | system:migration_016 |
| canonical_commit | `967df7a181b7da43d9a45f2c9a01eff3aa920e62` |
| matchar runtime SHA | **ja** |
| secrets exposed | **false** |
| --canonical-commit | ej använd (build-metadata path verifierad) |

`/admin/system/status` deployment.current_build: commit_sha=967df7a181b7, release_id=rc-967df7a181b7, status=healthy

## Safety (pre vs post deploy)
| Check | Result |
|-------|--------|
| jobs delta | 0 |
| approvals delta | 0 |
| scheduler | paused (oförändrad) |
| credentials changed | false (gmail/visma fingerprint match) |
| activation snapshots changed | false |
| onboarding sessions changed | false |
| tenant settings | config_version=5, timezone=Europe/Stockholm (oförändrat) |
| Gmail scans | 0 |
| external calls/writes | 0 |
| invitations | 0 |
| credentials_exposed | false |

## Gates (pre-merge)
- canonical + migration 016: 29 passed
- Customer Settings + Slice B + security: 130 passed
- R1 regression + E2E: PASS
- Full pytest: 3872 passed vs main 3859 — new_product_regressions=0

## Operational notes
- Backfill i container kräver `PYTHONPATH=/app` (deploy-script avbröts på detta steg men dry-run kördes manuellt och lyckades).
- Commit 2 (pilot role/browser verifier) **ej påbörjad** enligt instruktion.

## Beslut
| Gate | Result |
|------|--------|
| Commit 1 | **PASS** |
| Deploy | **PASS** |
| canonical_commit-fix verifierad | **ja** |
| Rollback behövs | **nej** |
| Redo för Commit 2 | **ja** (väntar på explicit start) |
