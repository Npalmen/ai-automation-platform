#!/usr/bin/env bash
sudo docker exec krowolf-db-1 psql -U postgres -d ai_platform -c "SELECT id, tenant_id, alert_type, status FROM operator_alerts WHERE status='open';"
