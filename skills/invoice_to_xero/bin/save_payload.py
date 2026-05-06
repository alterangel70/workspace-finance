#!/usr/bin/env python3
"""
Lobster step 5: save the xero-payload JSON produced by llm-task to disk.

stdin:  llm-task output  -- the raw xero-payload JSON object
stdout: confirmation envelope  -- { ok, saved_to }
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
args = parser.parse_args()

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"ERROR: llm-task returned invalid JSON: {e}", file=sys.stderr)
    sys.exit(1)

# Always force Reference to the extracted invoice number so Xero shows the
# correct supplier invoice reference regardless of what the LLM chose.
extraction_path = pathlib.Path(args.case_dir) / 'extraction.json'
if extraction_path.exists():
    try:
        ex = json.loads(extraction_path.read_text())
        invoice_number = ex.get('invoice_number') or ''
        if invoice_number:
            payload['Reference'] = invoice_number
    except Exception:
        pass  # non-fatal: LLM value is kept as-is


def _normalise_date(val):
    """Normalise a date string to ISO 8601 YYYY-MM-DD. Returns original on failure."""
    if not val or not isinstance(val, str):
        return val
    val = val.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val):
        return val
    for fmt in ('%d-%b-%Y', '%d/%m/%Y', '%m/%d/%Y', '%d %B %Y', '%B %d, %Y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.datetime.strptime(val, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return val  # validate_payload.py will catch non-conforming formats


payload['Date'] = _normalise_date(payload.get('Date'))
if payload.get('DueDate'):
    payload['DueDate'] = _normalise_date(payload['DueDate'])

out_file = pathlib.Path(args.case_dir) / 'xero-payload.json'
out_file.write_text(json.dumps(payload, indent=2))

print(json.dumps({"ok": True, "saved_to": str(out_file)}))
