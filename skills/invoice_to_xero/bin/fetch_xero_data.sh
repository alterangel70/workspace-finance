#!/usr/bin/env bash
set -euo pipefail

# fetch_xero_data.sh — Fetch Xero contacts (with optional search), active accounts,
# and active tax rates in a single call. Returns a combined JSON object:
# { "contacts": [...], "accounts": [...], "tax_rates": [...] }
#
# Usage:
#   fetch_xero_data.sh [--search "<supplier_name>"] [--connection-id "xero-default"]
#
# Use this instead of calling list_xero_contacts.sh, list_xero_accounts.sh, and
# list_xero_tax_rates.sh separately. One exec call covers all three lookups.

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.env
[[ -f "${_DIR}/../config.env" ]] && source "${_DIR}/../config.env"

: "${M365_XERO_BASE_URL:?M365_XERO_BASE_URL is not set}"
: "${M365_XERO_API_KEY:?M365_XERO_API_KEY is not set}"

CONNECTION_ID="xero-default"
SEARCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --connection-id) CONNECTION_ID="$2"; shift 2 ;;
    --search)        SEARCH="$2";        shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

ENCODED_CONNECTION="$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$CONNECTION_ID")"

# Build contacts URL
CONTACTS_URL="${M365_XERO_BASE_URL}/v1/xero/contacts?connection_id=${ENCODED_CONNECTION}"
if [[ -n "$SEARCH" ]]; then
  ENCODED_SEARCH="$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$SEARCH")"
  CONTACTS_URL="${CONTACTS_URL}&search=${ENCODED_SEARCH}"
fi

ACCOUNTS_URL="${M365_XERO_BASE_URL}/v1/xero/accounts?connection_id=${ENCODED_CONNECTION}&status=ACTIVE"
TAX_RATES_URL="${M365_XERO_BASE_URL}/v1/xero/tax-rates?connection_id=${ENCODED_CONNECTION}&status=ACTIVE"

AUTH_HEADER="Authorization: Bearer ${M365_XERO_API_KEY}"

_raw_contacts="$(curl -s -w "\n%{http_code}" -H "$AUTH_HEADER" "$CONTACTS_URL")"
_code_contacts="$(echo "$_raw_contacts" | tail -1)"
contacts_json="$(echo "$_raw_contacts" | head -n -1)"
if [[ "$_code_contacts" -lt 200 || "$_code_contacts" -ge 300 ]]; then
  echo "ERROR: /v1/xero/contacts returned HTTP ${_code_contacts}: ${contacts_json}" >&2; exit 1
fi

_raw_accounts="$(curl -s -w "\n%{http_code}" -H "$AUTH_HEADER" "$ACCOUNTS_URL")"
_code_accounts="$(echo "$_raw_accounts" | tail -1)"
accounts_json="$(echo "$_raw_accounts" | head -n -1)"
if [[ "$_code_accounts" -lt 200 || "$_code_accounts" -ge 300 ]]; then
  echo "ERROR: /v1/xero/accounts returned HTTP ${_code_accounts}: ${accounts_json}" >&2; exit 1
fi

_raw_tax_rates="$(curl -s -w "\n%{http_code}" -H "$AUTH_HEADER" "$TAX_RATES_URL")"
_code_tax_rates="$(echo "$_raw_tax_rates" | tail -1)"
tax_rates_json="$(echo "$_raw_tax_rates" | head -n -1)"
if [[ "$_code_tax_rates" -lt 200 || "$_code_tax_rates" -ge 300 ]]; then
  echo "ERROR: /v1/xero/tax-rates returned HTTP ${_code_tax_rates}: ${tax_rates_json}" >&2; exit 1
fi

python3 - "$contacts_json" "$accounts_json" "$tax_rates_json" <<'PYEOF'
import json, sys

contacts  = json.loads(sys.argv[1])
accounts  = json.loads(sys.argv[2])
tax_rates = json.loads(sys.argv[3])

print(json.dumps({
    "contacts":  contacts.get("contacts", []),
    "accounts":  accounts.get("accounts", []),
    "tax_rates": tax_rates.get("tax_rates", []),
}))
PYEOF
