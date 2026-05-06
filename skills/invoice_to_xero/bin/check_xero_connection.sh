#!/usr/bin/env bash
# check_xero_connection.sh — Lobster step 0: verify Xero connection before any workflow work.
# Exits 1 with a clear message if the connection is not valid, instead of failing
# obscurely later inside fetch_xero_data.sh.
set -euo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.env
[[ -f "${_DIR}/../config.env" ]] && source "${_DIR}/../config.env"

: "${M365_XERO_BASE_URL:?M365_XERO_BASE_URL is not set}"
: "${M365_XERO_API_KEY:?M365_XERO_API_KEY is not set}"

CONNECTION_ID="${1:-xero-default}"

result="$(curl -sf \
  -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
  "${M365_XERO_BASE_URL}/v1/connections/${CONNECTION_ID}/status" \
  || { echo "ERROR: could not reach proxy at ${M365_XERO_BASE_URL} — is the integration service running?" >&2; exit 1; })"

status="$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")"

if [[ "$status" != "valid" ]]; then
  echo "ERROR: Xero connection '${CONNECTION_ID}' is '${status}' — re-authorise before retrying." >&2
  echo "Run: curl -sf -H 'Authorization: Bearer \${M365_XERO_API_KEY}' '\${M365_XERO_BASE_URL}/v1/oauth/xero/authorize?connection_id=${CONNECTION_ID}'" >&2
  exit 1
fi

echo "$result"
