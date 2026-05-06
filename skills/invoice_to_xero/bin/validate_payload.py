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
import re
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
elif not re.match(r'^\d{4}-\d{2}-\d{2}$', str(p.get('Date', ''))):
    errors.append(f"Date must be YYYY-MM-DD, got: {p.get('Date')!r}")

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
extraction_path = case_dir / 'extraction.json'
ex = {}
if extraction_path.exists():
    try:
        ex = json.loads(extraction_path.read_text())
    except Exception:
        ex = {}

supplier_name = ex.get('supplier_name') or 'N/A'
invoice_number_ex = ex.get('invoice_number') or p.get('InvoiceNumber') or 'N/A'
date_ex = ex.get('invoice_date') or ex.get('date') or p.get('Date')
due_date_ex = ex.get('due_date')
currency_ex = ex.get('currency') or p.get('CurrencyCode')

# Load tax rate lookup written as a side-effect by combine_context.py
xero_rates_path = case_dir / 'xero-rates.json'
xero_rates = {}
if xero_rates_path.exists():
    try:
        xero_rates = json.loads(xero_rates_path.read_text())
    except Exception:
        xero_rates = {}

line_items_text = []
for li in line_items:
    desc = (li.get('Description') or '').strip()
    if len(desc) > 90:
        desc = desc[:90] + '…'
    qty = li.get('Quantity') or 1
    unit = li.get('UnitAmount') or 0
    account = li.get('AccountCode')
    tax_type = li.get('TaxType') or 'none'

    net = qty * unit
    rate = xero_rates.get(tax_type, 0.0) if tax_type != 'none' else 0.0
    tax_amt = net * rate

    if tax_type != 'none' and rate:
        tax_label = f"{tax_type} ({int(round(rate * 100))}%)"
    elif tax_type != 'none':
        tax_label = tax_type
    else:
        tax_label = 'none'

    line_items_text.append(
        f"- {desc}\n"
        f"  Net: {'%.2f' % net} {currency_ex}"
        f" • Tax: {'%.2f' % tax_amt} {currency_ex} ({tax_label})"
        f" • Account: {account}"
    )

# Totals calculated from payload — numbers match exactly what Xero will receive
subtotal_net = sum(
    (li.get('UnitAmount') or 0) * (li.get('Quantity') or 1)
    for li in line_items
)
vat_total = sum(
    (li.get('UnitAmount') or 0) * (li.get('Quantity') or 1)
    * xero_rates.get(li.get('TaxType') or '', 0.0)
    for li in line_items
)
total = subtotal_net + vat_total

# User-facing approval preview (JSON-wrapped so Lobster output[] is machine-readable)
summary = (
    f"Supplier: {supplier_name}\n"
    f"Invoice #: {invoice_number_ex}\n"
    f"Date: {date_ex or '—'}\n"
    f"Due date: {due_date_ex or '—'}\n"
    f"Currency: {currency_ex or '—'}\n"
    f"Line items:\n" + "\n".join(line_items_text) + "\n\n"
    f"Subtotal (net): {'%.2f' % subtotal_net} {currency_ex}\n"
    f"Tax: {'%.2f' % vat_total} {currency_ex}\n"
    f"Total: {'%.2f' % total} {currency_ex}"
)

print(json.dumps({"ok": True, "preview": summary}))
