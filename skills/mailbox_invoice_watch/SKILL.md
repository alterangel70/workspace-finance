---
name: mailbox_invoice_watch
description: >
  Periodic mailbox scan that detects likely invoice emails and surfaces them for
  human review. Handles deduplication, candidate persistence, and the approval
  gate before any extraction. Does NOT extract or submit invoices — that is the
  job of the invoice_to_xero skill, triggered only after explicit user approval.
license: MIT
metadata:
  author: openclaw
  version: "1.0.0"
allowed-tools: lobster
---

# mailbox_invoice_watch

## Purpose

Scan the Zoho INBOX for emails that are likely invoices, persist new candidates
locally, and notify the user when something new is found.

This skill covers only the scan-and-notify phase. Extraction and Xero submission
are handled by the `invoice_to_xero` skill and must never start without the
user's explicit approval in the current session.

---

## When to use this skill

- When a heartbeat fires (cron-driven periodic check).
- When the user asks "check the mailbox for invoices", "are there any new invoice
  emails", or similar.
- When the user manually asks you to run the scan.

Do NOT use this skill to extract or process invoices. For that, use `invoice_to_xero`.

---

## Workflow

The only workflow in this skill is `scan_invoice_mailbox.lobster`.
Always run it via the Lobster tool, not via raw shell commands.

```json
{
  "action": "run",
  "pipeline": "/home/ao/.openclaw/workspace-finance/skills/mailbox_invoice_watch/scan_invoice_mailbox.lobster",
  "timeoutMs": 90000
}
```

Optional args (all have defaults):

| Arg | Default | Description |
|-----|---------|-------------|
| `config` | `skills/claw-mail/config.yaml` | Path to claw-mail config |
| `account` | `zoho` | Mail account name |
| `folder` | `INBOX` | IMAP folder |
| `limit` | `25` | Max messages to fetch |
| `min_score` | `1` | Minimum heuristic score to keep a candidate |

---

## Output — scan summary JSON

The workflow outputs a JSON object on `scan.stdout`:

```json
{
  "ok": true,
  "scanned": 25,
  "new_candidates": 2,
  "skipped_known": 5,
  "skipped_low_score": 18,
  "items": [
    {
      "id": "inv-a1b2c3d4e5f60001",
      "subject": "Invoice #2026-042 for April services",
      "sender_address": "billing@supplier.com",
      "date": "2026-04-30T09:00:00Z",
      "score": 3,
      "attachment_count": 1
    }
  ]
}
```

### How to interpret it

- `new_candidates` — number of newly discovered candidates this run.
  Zero means nothing new; stay silent. Greater than zero means notify.
- `skipped_known` — already seen in a previous scan; normal, do not mention these.
- `skipped_low_score` — emails that scored below the threshold; not interesting.
- Each `items` entry gives you enough to write a one-line summary per candidate.

---

## Candidate storage

Each candidate is stored as a JSON file:

```
data/mailbox/pending/<pending-id>.json
```

Example pending item fields:

```json
{
  "id": "inv-a1b2c3d4e5f60001",
  "subject": "Invoice #2026-042 for April services",
  "sender_address": "billing@supplier.com",
  "sender_name": "Supplier Ltd",
  "date": "2026-04-30T09:00:00Z",
  "body_summary": "Please find attached...",
  "attachment_info": [
    {"filename": "invoice-042.pdf", "content_type": "application/pdf", "size": 48000, "saved_path": "/..."}
  ],
  "status": "pending",
  "scan_score": 3
}
```

When attachment bytes were present in the fetch payload, the file has already
been saved to disk at `saved_path`. Use that path when handing off to
`invoice_to_xero`.

---

## How to summarise new candidates

When `new_candidates > 0`, write one line per item using the fields from the
summary (not the full pending JSON — the summary fields are enough):

> **{subject}** — From: {sender_address} — {date, date part only} — {attachment_count} attachment(s)

If you want to show users the original attachment filenames (recommended), use:

> **{subject}** — From: {sender_address} — {date, date part only} — {attachment_filenames}

For multiple attachments, show a comma-separated list of filenames (e.g., "Invoice1.pdf, Invoice2.pdf").

Example:

> **Invoice #2026-042 for April services** — From: billing@supplier.com — 2026-04-30 — 1 attachment(s)

After listing all items, ask the user whether to proceed. See AGENTS.md §Mailbox
Invoice Watch for the exact wording.

---

## Approval gate — mandatory

**Never proceed to extraction without explicit approval.**

- Running the scan is always permitted (it is read-only).
- Surfacing candidates to the user is always permitted.
- Starting extraction (`invoice_to_xero`) requires the user to say so explicitly
  in this session.

What counts as explicit approval:
- "yes", "go ahead", "process them"
- Confirmation of a specific item by ID (e.g. "inv-a1b2c3d4e5f60001") or subject
- An unambiguous instruction such as "process the April invoice from Supplier Ltd"

What does NOT count as approval:
- The heartbeat firing (the cron does not approve anything)
- A prior session where candidates were listed
- Ambiguous statements like "sounds good" in unrelated context

When approval is given for one or more items, hand off to `invoice_to_xero` for
each approved item, one at a time. Before starting:

1. Read the full pending item from `data/mailbox/pending/<id>.json`.
2. Check `attachment_info[*].saved_path` for a non-null entry — that is the
   local PDF path to hand to `invoice_to_xero` as the invoice file.
3. If `saved_path` is null for all attachments (the email had no downloadable
   file), tell the user and ask them to provide the invoice file manually.
4. Read the `invoice_to_xero` SKILL.md before starting that workflow.

---

## Silence rule

If `new_candidates == 0`, stop immediately. Do not send any message.
Reply `HEARTBEAT_OK` if this was triggered by a heartbeat.
