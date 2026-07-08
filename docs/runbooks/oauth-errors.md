# Runbook: OAuth and Gmail Token Errors

> **Safety:** Never print or log OAuth tokens. All token updates must use the server directly.
> **Lesson learned (Phase K):** `docker compose restart` does NOT re-read `.env.production`. Always use `docker compose up -d` after env changes.

---

## Overview

The platform uses long-lived refresh tokens for Gmail. Access tokens expire in ~1 hour. When the refresh token is invalid or the OAuth client credentials change, the system returns `503` and logs `invalid_grant`. This runbook covers diagnosis and recovery.

---

## Error signatures

| Error | Cause |
|-------|-------|
| `503` with `invalid_grant` | Refresh token expired, revoked, or issued for a different OAuth client |
| `503` with `unauthorized_client` | `GOOGLE_OAUTH_CLIENT_ID` or `GOOGLE_OAUTH_CLIENT_SECRET` does not match the token's origin client |
| `503` with `invalid_client` | Wrong client ID/secret combination — check Google Cloud Console |
| `Incomplete OAuth refresh credentials` in startup logs | One or more of the 4 Gmail env vars is missing |

All four env vars are required for automatic token refresh:
```
GOOGLE_MAIL_ACCESS_TOKEN
GOOGLE_OAUTH_REFRESH_TOKEN
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
```

---

## Step 1: Confirm the error

```bash
# Check integration health
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Look for: gmail.status, gmail.last_error_message, gmail.recommended_action

# Check logs for the exact error
ssh ubuntu@api.krowolf.se \
  "sudo docker compose -f /opt/krowolf/docker-compose.prod.yml logs --tail=200 app | grep -i 'gmail\|oauth\|invalid_grant\|refresh'"
```

---

## Step 2: Test token refresh directly (without restarting app)

```bash
# On the server — test refresh manually
ssh ubuntu@api.krowolf.se bash -s <<'EOF'
REFRESH=$(sudo grep '^GOOGLE_OAUTH_REFRESH_TOKEN=' /opt/krowolf/.env.production | cut -d= -f2-)
CLIENT_ID=$(sudo grep '^GOOGLE_OAUTH_CLIENT_ID=' /opt/krowolf/.env.production | cut -d= -f2-)
CLIENT_SECRET=$(sudo grep '^GOOGLE_OAUTH_CLIENT_SECRET=' /opt/krowolf/.env.production | cut -d= -f2-)
curl -sS -X POST https://oauth2.googleapis.com/token \
  -d "client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&refresh_token=$REFRESH&grant_type=refresh_token" \
  | python3 -m json.tool
EOF
# Expect: {"access_token":"ya29.xxx","expires_in":3599,"token_type":"Bearer"}
# Error: {"error":"invalid_grant"} → refresh token is bad
# Error: {"error":"unauthorized_client"} → client credentials don't match token origin
```

---

## Step 3: Update tokens

Obtain a fresh refresh token via Google OAuth Playground:
1. Go to [https://developers.google.com/oauthplayground/](https://developers.google.com/oauthplayground/)
2. Configure with your OAuth client (gear icon → use your own OAuth credentials)
3. Select Gmail API scopes: `https://mail.google.com/`
4. Complete the OAuth flow with the Gmail account
5. Exchange authorization code for tokens
6. Copy `refresh_token` and `access_token`

Update on the server (never paste tokens in chat):
```bash
# SSH to server — update tokens interactively
ssh ubuntu@api.krowolf.se
sudo nano /opt/krowolf/.env.production
# Update: GOOGLE_MAIL_ACCESS_TOKEN=<new>
#         GOOGLE_OAUTH_REFRESH_TOKEN=<new>
# Save and exit

# Recreate container (NOT restart — restart does not re-read .env.production)
cd /opt/krowolf
sudo docker compose -f docker-compose.prod.yml up -d app

# Verify health
curl -sS https://api.krowolf.se/health
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
```

---

## Step 4: Verify fix

```bash
# Dry-run inbox sync (reads inbox but creates no jobs)
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox?dry_run=true" \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expect: HTTP 200, "dry_run": true, no new jobs created

# If dry run succeeds, do a real sync
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox?dry_run=false" \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## Step 5: If OAuth client changed (new CLIENT_ID / CLIENT_SECRET)

A refresh token is bound to the specific OAuth client that generated it. If you change `GOOGLE_OAUTH_CLIENT_ID` or `GOOGLE_OAUTH_CLIENT_SECRET`, the old refresh token will fail with `unauthorized_client`.

**You must generate a new refresh token using the new client** (repeat Step 3 above with the new client credentials configured in Google OAuth Playground).

---

## Prevention

- Refresh tokens can expire after ~6 months of inactivity or if the Google account owner revokes app access.
- Check `GET /integrations/health` weekly during pilot to catch token issues early.
- Set up alerts: `PUT /alerts/config` with `recipient_email` to receive integration error alerts.

---

## Related runbooks

- `docs/runbooks/integration-errors.md` — for Monday/Fortnox errors
- `docs/runbooks/failed-jobs.md` — for jobs that failed due to OAuth errors
