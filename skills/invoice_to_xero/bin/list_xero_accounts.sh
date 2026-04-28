#!/usr/bin/env bash
set -euo pipefail

# list_xero_accounts.sh — List Xero chart-of-accounts entries
# Required env: M365_XERO_BASE_URL, M365_XERO_API_KEY

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.env
[[ -f "${_DIR}/../config.env" ]] && source "${_DIR}/../config.env"

: "${M365_XERO_BASE_URL:?M365_XERO_BASE_URL is not set}"
: "${M365_XERO_API_KEY:?M365_XERO_API_KEY is not set}"

CONNECTION_ID="xero-default"
STATUS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --connection-id) CONNECTION_ID="$2"; shift 2 ;;
    --status)        STATUS="$2";        shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

URL="${M365_XERO_BASE_URL}/v1/xero/accounts?connection_id=${CONNECTION_ID}"
[[ -n "$STATUS" ]] && URL="${URL}&status=${STATUS}"

curl -sf \
  -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
  "${URL}" \
  || { echo "curl failed (exit $?): request to /v1/xero/accounts failed" >&2; exit 1; }
