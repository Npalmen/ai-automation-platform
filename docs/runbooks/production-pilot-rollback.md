# Production pilot rollback runbook

## Application rollback

1. Identify rollback target from release manifest (`rollback_target`, prior image digest)
2. Deploy previous image digest (RC tag)
3. Verify `GET /health` returns 200
4. Verify runtime SHA matches expected rollback commit

## Configuration rollback

```text
snapshot → activate phase → verify → pause → restore → verify hash match
```

```bash
python scripts/production_pilot/restore_baseline.py --execute
```

## Database

- Backup required before any migration (`backup_reference` in release manifest)
- No automatic destructive rollback migrations
- Pilot data must not be mixed with eval/campaign data

## Incident stop

On safety incident:

1. Pause automation immediately
2. Disable Gmail replies
3. Disable shadow promotion
4. Restore baseline snapshot
5. Verify config hash match
