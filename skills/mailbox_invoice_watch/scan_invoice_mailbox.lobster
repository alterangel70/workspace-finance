name: scan_invoice_mailbox

# Scan the Zoho INBOX for likely invoice emails and persist pending items.
#
# Each new candidate is saved as a JSON file in:
#   data/mailbox/pending/<pending-id>.json
#
# Deduplication: items already recorded in a previous scan are silently skipped.
# This workflow is deliberately NOT wired to cron — run it manually first to
# verify scan quality before scheduling.
#
# ─── Manual invocation (OpenClaw lobster tool) ───────────────────────────────
#   { "action": "run",
#     "pipeline": "/home/ao/.openclaw/workspace-finance/skills/mailbox_invoice_watch/scan_invoice_mailbox.lobster",
#     "timeoutMs": 90000 }
#
# With custom args:
#   { "action": "run",
#     "pipeline": "..../scan_invoice_mailbox.lobster",
#     "argsJson": "{\"limit\":\"50\",\"min_score\":\"2\"}",
#     "timeoutMs": 90000 }
#
# ─── CLI invocation (lobster binary) ─────────────────────────────────────────
#   lobster run --file scan_invoice_mailbox.lobster
#   lobster run --file scan_invoice_mailbox.lobster --args-json '{"limit":"50"}'
#
# ─── Direct shell (bypass Lobster, useful for quick debugging) ───────────────
#   cd /home/ao/.openclaw/workspace-finance/skills/claw-mail
#   python3 scripts/fetch_mail.py --config config.yaml --account zoho --format json |
#     python3 /home/ao/.openclaw/workspace-finance/skills/mailbox_invoice_watch/bin/scan_inbox.py \
#       --incoming-dir /home/ao/.openclaw/workspace-finance/data/mailbox/pending

args:
  # Path to the claw-mail config.yaml
  config:
    default: "/home/ao/.openclaw/workspace-finance/skills/claw-mail/config.yaml"
  # Mail account name (must match an entry in config.yaml)
  account:
    default: "zoho"
  # IMAP folder to scan
  folder:
    default: "INBOX"
  # Max messages to fetch from the mailbox (0 = use account default)
  limit:
    default: "25"
  # Minimum heuristic score to classify an email as a candidate:
  #   2 = subject keyword match only (more precise)
  #   1 = any invoice-type attachment OR subject match (wider net, default)
  min_score:
    default: "1"

steps:
  # Step 1: fetch recent messages from the mailbox as JSON.
  # Uses $LOBSTER_ARG_* env vars to avoid shell injection from arg values.
  - id: fetch
    run: |
      python3 /home/ao/.openclaw/workspace-finance/skills/claw-mail/scripts/fetch_mail.py \
        --config "$LOBSTER_ARG_CONFIG" \
        --account "$LOBSTER_ARG_ACCOUNT" \
        --folder "$LOBSTER_ARG_FOLDER" \
        --limit "$LOBSTER_ARG_LIMIT" \
        --format json

  # Step 2: filter for invoice candidates and persist new pending items.
  # Reads the fetch JSON from stdin; writes one JSON file per new item.
  # Outputs a summary JSON (scanned / new_candidates / skipped counts).
  - id: scan
    stdin: $fetch.stdout
    run: |
      python3 /home/ao/.openclaw/workspace-finance/skills/mailbox_invoice_watch/bin/scan_inbox.py \
        --incoming-dir /home/ao/.openclaw/workspace-finance/data/mailbox/pending \
        --min-score "$LOBSTER_ARG_MIN_SCORE"
