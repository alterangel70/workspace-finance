#!/usr/bin/env bash
set -euo pipefail

# create_xero_draft.sh — Create a DRAFT Xero accounts-payable invoice from a
# Xero-format JSON checkpoint file (step2.json) produced by the invoice pipeline.
# Supports multiple line items. Always creates DRAFT — never authorises.
# Required env: M365_XERO_BASE_URL, M365_XERO_API_KEY

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.env
[[ -f "${_DIR}/../config.env" ]] && source "${_DIR}/../config.env"

: "${M365_XERO_BASE_URL:?M365_XERO_BASE_URL is not set}"
: "${M365_XERO_API_KEY:?M365_XERO_API_KEY is not set}"

JSON_FILE=""
IDEMPOTENCY_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json-file)       JSON_FILE="$2";       shift 2 ;;
    --idempotency-key) IDEMPOTENCY_KEY="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$JSON_FILE" ]] || { echo "--json-file is required" >&2; exit 1; }
[[ -f "$JSON_FILE" ]] || { echo "File not found: $JSON_FILE" >&2; exit 1; }

if [[ -z "$IDEMPOTENCY_KEY" ]]; then
  IDEMPOTENCY_KEY="$(python3 -c 'import uuid; print(uuid.uuid4())')"
fi

PAYLOAD="$(python3 - "$JSON_FILE" << 'PYEOF'
import json, sys, datetime

data = json.load(open(sys.argv[1]))

# --- Required fields ---
contact_id = data.get('Contact', {}).get('ContactID', '')
if not contact_id:
    print("ERROR: Contact.ContactID is missing in xero-payload.json", file=sys.stderr)
    sys.exit(1)

currency_code = data.get('CurrencyCode') or 'EUR'

due_date = data.get('DueDate') or data.get('Date')
if not due_date:
    due_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

# --- Line items: full explicit mapping, no silent drops ---
raw_items = data.get('LineItems', [])
if not raw_items:
    print("ERROR: LineItems is empty in xero-payload.json", file=sys.stderr)
    sys.exit(1)

line_items = []
for i, li in enumerate(raw_items):
    for field in ('Description', 'Quantity', 'UnitAmount', 'AccountCode'):
        if li.get(field) is None:
            print(f"ERROR: LineItems[{i}].{field} is missing", file=sys.stderr)
            sys.exit(1)
    item = {
        'description':  li['Description'],
        'quantity':     li['Quantity'],
        'unit_amount':  li['UnitAmount'],
        'account_code': str(li['AccountCode']),
    }
    if li.get('TaxType'):
        item['tax_type'] = li['TaxType']
    line_items.append(item)

# --- Assemble proxy payload ---
payload = {
    'connection_id': 'xero-default',
    'contact_id':    contact_id,
    'line_items':    line_items,
    'due_date':      due_date,
    'currency_code': currency_code,
}

date_val = data.get('Date')
if date_val:
    payload['date'] = date_val

ref = data.get('Reference') or data.get('InvoiceNumber')
if ref:
    payload['reference'] = ref

print(json.dumps(payload))
PYEOF
)"

echo "PAYLOAD:" >&2
echo "$PAYLOAD" >&2

TMPFILE="$(mktemp)"
HTTP_STATUS="$(curl -s -o "$TMPFILE" -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d "$PAYLOAD" \
  "${M365_XERO_BASE_URL}/v1/xero/invoices")"
RESPONSE_BODY="$(cat "$TMPFILE")"
rm -f "$TMPFILE"

if [[ "$HTTP_STATUS" -lt 200 || "$HTTP_STATUS" -ge 300 ]]; then
  echo "ERROR: Xero API returned HTTP ${HTTP_STATUS}: ${RESPONSE_BODY}" >&2
  exit 1
fi

echo "$RESPONSE_BODY"
