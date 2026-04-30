#!/usr/bin/env python3
"""
Lobster step 6: validate xero-payload.json before the approval gate.

Reads case_dir/xero-payload.json from disk.
Exits 0 and prints a human-readable summary to stdout (shown to user at approval step).
Exits 1 and prints errors to stderr (Lobster hard-stops the workflow).
"""
import argparse
import json
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
args = parser.parse_args()

case_dir = pathlib.Path(args.case_dir)
payload_file = case_dir / 'xero-payload.json'

if not payload_file.exists():
    print("ERROR: xero-payload.json not found", file=sys.stderr)
    sys.exit(1)

try:
    p = json.loads(payload_file.read_text())
except json.JSONDecodeError as e:
    print(f"ERROR: xero-payload.json is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

errors = []

if p.get('Type') != 'ACCPAY':
    errors.append(f"Type must be ACCPAY, got: {p.get('Type')!r}")

contact_id = p.get('Contact', {}).get('ContactID', '')
if not contact_id:
    errors.append("Contact.ContactID is missing or empty")

if not p.get('Date'):
    errors.append("Date is missing")

if not p.get('CurrencyCode'):
    errors.append("CurrencyCode is missing")

if not p.get('Reference') and not p.get('InvoiceNumber'):
    errors.append("Reference or InvoiceNumber is required")

line_items = p.get('LineItems', [])
if not line_items:
    errors.append("LineItems is empty or missing")
else:
    for i, li in enumerate(line_items):
        if not li.get('Description'):
            errors.append(f"LineItems[{i}].Description is missing")
        if not isinstance(li.get('Quantity'), (int, float)):
            errors.append(f"LineItems[{i}].Quantity must be a number")
        if not isinstance(li.get('UnitAmount'), (int, float)):
            errors.append(f"LineItems[{i}].UnitAmount must be a number")
        if not li.get('AccountCode'):
            errors.append(f"LineItems[{i}].AccountCode is missing")

if errors:
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

# Build human-readable summary for the approval gate
ref = p.get('Reference') or p.get('InvoiceNumber', 'N/A')
lines_summary = '\n'.join(
    f"  - {li.get('Description', '')[:70]}\n"
    f"    {li.get('Quantity')} x {li.get('UnitAmount')} {p.get('CurrencyCode', '')} "
    f"| AccountCode: {li.get('AccountCode')} | Tax: {li.get('TaxType', 'none')}"
    for li in line_items
)
total_net = sum(
    li.get('UnitAmount', 0) * li.get('Quantity', 0)
    for li in line_items
)

summary = (
    f"--- Invoice ready for Xero DRAFT creation ---\n"
    f"Reference:  {ref}\n"
    f"Contact ID: {contact_id}\n"
    f"Date:       {p.get('Date')} | Due: {p.get('DueDate', 'N/A')}\n"
    f"Currency:   {p.get('CurrencyCode')}\n"
    f"Line items:\n{lines_summary}\n"
    f"Net total:  {total_net:.2f} {p.get('CurrencyCode', '')}\n"
    f"----------------------------------------------\n"
    f"Approve to create DRAFT in Xero. Deny to cancel."
)

print(summary)
