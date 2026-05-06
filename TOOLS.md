# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

---

## Company Identity

- **Our company name**: Valletta Credit Finance Corporation Limited
- On any invoice we receive, **we are always the buyer/client — never the supplier**.
- If an extracted invoice has `supplier_name` matching our company name (or a close variant), the extraction is wrong — stop and ask the user to clarify which party is the supplier.
- Known name variants to treat as our own company: "Valletta Credit Finance", "VCF", "Valletta Credit Finance Corp"

---

## Email

- Default account: zoho
- Default mailbox: INBOX
- Use the `claw-mail` skill for all email tasks

---

## Xero Connection

**Check status:**
```bash
curl -sf \
  -H "Authorization: Bearer oclaw-dev-6c8c4c5f-7f5a-4a47-b9d0-5f2c1c0f8f1e" \
  "http://127.0.0.1:18432/v1/connections/xero-default/status"
# → {"status":"valid"} or {"status":"expired"} or {"status":"missing"}
```

**Status meanings:**

| Status    | Meaning                                        | Action required       |
|-----------|------------------------------------------------|-----------------------|
| `valid`   | Token active, all Xero calls will work         | None                  |
| `expired` | Refresh token expired (60-day idle limit)      | Full re-authorisation |
| `missing` | Connection never set up or Redis cleared       | Full re-authorisation |

**Re-authorise (step by step):**

1. Get the authorisation URL:
   ```bash
   curl -sf \
     -H "Authorization: Bearer oclaw-dev-6c8c4c5f-7f5a-4a47-b9d0-5f2c1c0f8f1e" \
     "http://127.0.0.1:18432/v1/oauth/xero/authorize?connection_id=xero-default"
   # → {"url":"https://login.xero.com/identity/connect/authorize?..."}
   ```
2. Open the returned URL in a browser and complete Xero login/consent.
3. After consent Xero redirects to `http://localhost:18432/v1/oauth/xero/callback?code=...&state=...`  
   The browser will show an error (expected — callback is not publicly routable). Copy the full URL from the address bar.
4. Extract `code` and `state` query parameters and POST to the callback manually:
   ```bash
   curl -sf -X POST \
     -H "Authorization: Bearer oclaw-dev-6c8c4c5f-7f5a-4a47-b9d0-5f2c1c0f8f1e" \
     "http://127.0.0.1:18432/v1/oauth/xero/callback?code=<CODE>&state=<STATE>"
   # → {"status":"ok"}
   ```
5. Re-run the status check — should return `{"status":"valid"}`.

**Keepalive note:** A weekly cron job (Monday 07:00 Malta) sends the finance agent a Xero status ping. This prevents the refresh token from expiring due to 60 days of inactivity. If the agent reports expiry, follow the re-authorisation steps above.