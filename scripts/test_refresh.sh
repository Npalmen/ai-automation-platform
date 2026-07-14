#!/bin/bash
set -e
CLIENT_ID=$(sudo grep '^GOOGLE_OAUTH_CLIENT_ID=' /opt/krowolf/.env.production | cut -d= -f2- | tr -d '\r\n')
CLIENT_SECRET=$(sudo grep '^GOOGLE_OAUTH_CLIENT_SECRET=' /opt/krowolf/.env.production | cut -d= -f2- | tr -d '\r\n')
REFRESH_TOKEN=$(sudo grep '^GOOGLE_OAUTH_REFRESH_TOKEN=' /opt/krowolf/.env.production | cut -d= -f2- | tr -d '\r\n')

echo "  CLIENT_ID=${CLIENT_ID}"
echo "  CLIENT_SECRET_LEN=${#CLIENT_SECRET}"
echo "  REFRESH_TOKEN_LEN=${#REFRESH_TOKEN}"

echo ""
echo "=== Token refresh test ==="
RESP=$(curl -sS -w '\n__HTTP__:%{http_code}' --max-time 15 \
  -X POST "https://oauth2.googleapis.com/token" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode "refresh_token=${REFRESH_TOKEN}" \
  --data-urlencode "grant_type=refresh_token")
RH=$(echo "$RESP" | grep -o '__HTTP__:[0-9]*' | cut -d: -f2)
RB=$(echo "$RESP" | sed '/__HTTP__:/d')
echo "  HTTP=${RH}"
echo "$RB" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  if 'access_token' in d:
    t=d['access_token']
    print('  PASS: got new access_token (len=%d)' % len(t))
    print('  expires_in:', d.get('expires_in'))
    print('  token_type:', d.get('token_type'))
  else:
    print('  FAIL: error=%s' % d.get('error'))
    print('  error_description:', d.get('error_description'))
except Exception as e:
  print('  parse error:', e)
" 2>/dev/null

unset CLIENT_ID CLIENT_SECRET REFRESH_TOKEN
echo "SECRETS_CLEARED"
