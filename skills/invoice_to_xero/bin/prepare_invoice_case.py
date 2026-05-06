#!/usr/bin/env python3
"""
Pre-pipeline setup: create the case directory, copy the source PDF, and write
extraction.json from stdin.

The agent calls this script instead of issuing ad-hoc mkdir/cp/python3 inline
commands, which would not match the exec-approvals allowlist.

Usage:
    echo '<extraction-json>' | python3 prepare_invoice_case.py \
        --case-dir /path/to/data/invoices/pending/<case-id> \
        --source-pdf /path/to/attachments/<file>.pdf

stdin:  extraction JSON object (as produced by the PDF parsing step)
stdout: { "ok": true, "case_dir": "...", "extraction_keys": [...] }
exits 1 on any error
"""
import argparse
import json
import pathlib
import shutil
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
parser.add_argument('--source-pdf', required=True)
args = parser.parse_args()

case_dir = pathlib.Path(args.case_dir)
source_pdf = pathlib.Path(args.source_pdf)

# --- validate inputs --------------------------------------------------------
if not source_pdf.exists():
    print(f"ERROR: source PDF not found: {source_pdf}", file=sys.stderr)
    sys.exit(1)

try:
    extraction = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"ERROR: stdin is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

if not isinstance(extraction, dict):
    print("ERROR: extraction JSON must be an object", file=sys.stderr)
    sys.exit(1)

# --- create case dir and copy PDF -------------------------------------------
case_dir.mkdir(parents=True, exist_ok=True)
dest_pdf = case_dir / "source"
shutil.copy2(source_pdf, dest_pdf)

# --- write extraction.json --------------------------------------------------
extraction_file = case_dir / "extraction.json"
extraction_file.write_text(json.dumps(extraction, indent=2))

print(json.dumps({
    "ok": True,
    "case_dir": str(case_dir),
    "extraction_keys": list(extraction.keys()),
}))
