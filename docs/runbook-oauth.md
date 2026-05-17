# Runbook: OAuth Recovery

## Syfte
Denna runbook täcker hur Gmail OAuth-token hanteras, förnyas och återställs vid token-expiry eller revocation under pilot.

## Bakgrund

Plattformen använder OAuth 2.0 för Gmail-integration (läsning och skrivning). Tokens lagras i tenant-inställningar och uppdateras automatiskt vid expiry, förutsatt att refresh_token är giltig.

## Token-struktur

```json
{
  "oauth": {
    "gmail": {
      "access_token": "...",
      "refresh_token": "...",
      "token_expiry": "2026-05-10T12:00:00Z",
      "email": "pilot@example.com"
    }
  }
}
```

## Kontrollera Token-status

```bash
# Hälsostatus för integrationer (visar om Gmail är OK)
GET /integrations/health
Header: X-API-Key: <tenant-key>

# Kontrollera pilot readiness
GET /pilot/readiness
Header: X-API-Key: <tenant-key>
```

Tecken på utgången token:
- `gmail.status` = `error` i integration health
- Inbox sync loggar `401 Unauthorized` eller `Token has been expired or revoked`
- Scheduler-log visar `GmailAuthError`

## Förnya Token (Automatisk)

Plattformen försöker automatiskt förnya access_token med refresh_token. Om refresh_token är giltig behövs ingen manuell åtgärd.

## Manuell Token Refresh

Om automatisk förnyelse misslyckas (t.ex. refresh_token revokad):

### Steg 1: Hämta ny token via Google OAuth-flöde

```bash
# Starta OAuth-callback endpoint
GET /auth/gmail/start?tenant_id=<tenant_id>
# Följ redirect till Google
# Kopiera authorization_code från callback-URL
```

### Steg 2: Skicka token till plattformen

```bash
POST /auth/gmail/callback
{
  "code": "<authorization_code>",
  "tenant_id": "<tenant_id>"
}
```

### Steg 3: Verifiera

```bash
GET /integrations/health
Header: X-API-Key: <tenant-key>
# systems.gmail.status ska vara "healthy"
```

## Vanliga Problem

### "Token has been expired or revoked"
- Orsak: Användaren har revokerat åtkomst i Google Account Settings, eller 6 månaders inaktivitet
- Lösning: Kör manuellt OAuth-flöde ovan

### "invalid_client"
- Orsak: OAuth-credentials (client_id/client_secret) har ändrats eller raderats
- Lösning: Skapa ny OAuth-app i Google Cloud Console, uppdatera env-variabler

### Gmail läser men skriver inte
- Kontrollera att OAuth-scope inkluderar `gmail.send` och `gmail.modify`
- Se Google Cloud Console → API & Services → OAuth consent screen → Scopes

## Miljövariabler

```bash
# Krävs i .env eller miljön
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-domain.com/auth/gmail/callback
```

## Säkerhet

- Lagra aldrig tokens i git
- Rotera client_secret vid misstänkt exponering via: `PUT /tenant/memory` (uppdatera oauth-sektionen)
- Varje tenant har egna OAuth-tokens — ett tenant-problem sprider sig inte till andra

## Microsoft Mail (framtida)

Microsoft-adapter finns men är inte fullt aktiverad. OAuth-flöde för Microsoft kräver:
- Azure App Registration
- `Mail.ReadWrite` + `Calendars.ReadWrite` permissions
- Egen callback endpoint (`/auth/microsoft/callback`)

Se `app/integrations/microsoft/` för aktuell implementationsstatus.

## Eskalering

Kontakta plattformsteamet om:
- OAuth-flödet returnerar oväntade fel
- Token förnyas inte automatiskt trots giltig refresh_token
- Multipla tenants förlorar Gmail-åtkomst samtidigt
