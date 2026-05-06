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

# If expired, attempt a lightweight Xero API call to trigger the integration
# service's auto-refresh (it refreshes the access token on any proxied request),
# then re-check the status before giving up.
if [[ "$status" == "expired" ]]; then
  echo "INFO: Xero connection '${CONNECTION_ID}' is expired — attempting auto-refresh via contacts ping..." >&2
  curl -sf \
    -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
    "${M365_XERO_BASE_URL}/v1/xero/contacts?connection_id=${CONNECTION_ID}&page_size=1" \
    > /dev/null 2>&1 || true
  result="$(curl -sf \
    -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
    "${M365_XERO_BASE_URL}/v1/connections/${CONNECTION_ID}/status" \
    || { echo "ERROR: could not reach proxy at ${M365_XERO_BASE_URL} after refresh attempt." >&2; exit 1; })"
  status="$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")"
  if [[ "$status" == "valid" ]]; then
    echo "INFO: Xero connection '${CONNECTION_ID}' successfully refreshed." >&2
  fi
fi

if [[ "$status" != "valid" ]]; then
  echo "ERROR: Xero connection '${CONNECTION_ID}' is '${status}' — re-authorise before retrying." >&2
  echo "Run: curl -sf -H 'Authorization: Bearer \${M365_XERO_API_KEY}' '\${M365_XERO_BASE_URL}/v1/oauth/xero/authorize?connection_id=${CONNECTION_ID}'" >&2
  exit 1
fi

echo "$result"
