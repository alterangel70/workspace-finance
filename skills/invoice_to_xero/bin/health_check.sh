#!/usr/bin/env bash
set -euo pipefail

# health_check.sh — Check liveness and dependency health of the m365-xero proxy
# No auth required. Returns {"status": "ok"|"degraded", "redis": "ok"|"error", "ms_graph": "ok"|"error"}

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../config.env
[[ -f "${_DIR}/../config.env" ]] && source "${_DIR}/../config.env"

: "${M365_XERO_BASE_URL:?M365_XERO_BASE_URL is not set}"

curl -sf \
  "${M365_XERO_BASE_URL}/health" \
  || { echo "curl failed (exit $?): request to /health failed" >&2; exit 1; }
