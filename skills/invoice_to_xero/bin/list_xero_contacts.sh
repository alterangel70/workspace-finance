#!/usr/bin/env bash
set -euo pipefail

# list_xero_contacts.sh — Search or list Xero contacts
# Required env: M365_XERO_BASE_URL, M365_XERO_API_KEY

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

QUERY="connection_id=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$CONNECTION_ID")"

if [[ -n "$SEARCH" ]]; then
  ENCODED_SEARCH="$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$SEARCH")"
  QUERY="${QUERY}&search=${ENCODED_SEARCH}"
fi

curl -sf \
  -H "Authorization: Bearer ${M365_XERO_API_KEY}" \
  "${M365_XERO_BASE_URL}/v1/xero/contacts?${QUERY}" \
  || { echo "curl failed (exit $?): request to /v1/xero/contacts failed" >&2; exit 1; }
