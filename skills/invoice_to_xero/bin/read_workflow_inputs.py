#!/usr/bin/env python3
"""
Lobster step 1: read extraction.json and vendor memory for this case.

Writes workflow_inputs.json to case_dir (so combine_context.py can read it
later from disk — needed because Lobster steps can only pipe one stdin at a time).

Also prints the same JSON to stdout (for any future chaining if needed).
"""
import argparse
import difflib
import json
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
parser.add_argument('--supplier-slug', required=True)
args = parser.parse_args()

case_dir = pathlib.Path(args.case_dir)
extraction_file = case_dir / 'extraction.json'

if not extraction_file.exists():
    print(f"ERROR: extraction.json not found in {case_dir}", file=sys.stderr)
    sys.exit(1)

try:
    extraction = json.loads(extraction_file.read_text())
except json.JSONDecodeError as e:
    print(f"ERROR: extraction.json is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

# Vendors dir: case_dir is .../data/invoices/pending/<case-id>/
# so .../data/ is three levels up, then /vendors/
vendors_dir = case_dir.parent.parent.parent / 'vendors'
vendor_file = vendors_dir / f"{args.supplier_slug}.json"

vendor_memory = {}
if vendor_file.exists():
    try:
        vendor_memory = json.loads(vendor_file.read_text())
    except json.JSONDecodeError:
        vendor_memory = {}  # corrupt file — treat as no memory

if not vendor_memory and vendors_dir.exists():
    # Exact slug not found — try fuzzy match against available vendor slugs
    available_slugs = [p.stem for p in vendors_dir.glob('*.json')]
    close = difflib.get_close_matches(args.supplier_slug, available_slugs, n=1, cutoff=0.85)
    if close:
        fuzzy_file = vendors_dir / f"{close[0]}.json"
        print(f"INFO: no exact vendor match for '{args.supplier_slug}', using close match '{close[0]}'", file=sys.stderr)
        try:
            vendor_memory = json.loads(fuzzy_file.read_text())
        except json.JSONDecodeError:
            vendor_memory = {}

output = {
    "extraction": extraction,
    "vendor_memory": vendor_memory,
}

# Write to disk so combine_context.py can join it with xero data later
(case_dir / 'workflow_inputs.json').write_text(json.dumps(output))

print(json.dumps(output))
