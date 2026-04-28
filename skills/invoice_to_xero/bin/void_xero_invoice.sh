#!/usr/bin/env bash
set -euo pipefail

# void_xero_invoice.sh — Void a Xero invoice (irreversible)
# Required env: M365_XERO_BASE_URL, M365_XERO_API_KEY

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.env
[[ -f "${_DIR}/../config.env" ]] && source "${_DIR}/../config.env"

: "${M365_XERO_BASE_URL:?M365_XERO_BASE_URL is not set}"
: "${M365_XERO_API_KEY:?M365_XERO_API_KEY is not set}"

CONNECTION_ID="xero-default"
INVOICE_ID=""
IDEMPOTENCY_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --connection-id)   CONNECTION_ID="$2";   shift 2 ;;
    --invoice-id)      INVOICE_ID="$2";      shift 2 ;;
    --idempotency-key) IDEMPOTENCY_KEY="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$INVOICE_ID" ]] || { echo "--invoice-id is required" >&2; exit 1; }

if [[ -z "$IDEMPOTENCY_KEY" ]]; then
  IDEMPOTENCY_KEY="$(python3 -c 'import uuid; print(uuid.uuid4())')"
fi

PAYLOAD="$(python3 -c "
import json, sys
print(json.dumps({'connection_id': sys.argv[1]}))" "$CONNECTION_ID")"

curl -sf \
  -X POST \
  -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ${IDEMPOTENCY_KEY}" \
  -d "$PAYLOAD" \
  "${M365_XERO_BASE_URL}/v1/xero/invoices/${INVOICE_ID}/void" \
  || { echo "curl failed (exit $?): request to /v1/xero/invoices/${INVOICE_ID}/void failed" >&2; exit 1; }
