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

# Best-effort mapping of payload line items to extraction line items (by index)
li_summaries = []
for i, li in enumerate(line_items):
    desc = li.get('Description') or ''
    qty = li.get('Quantity')
    unit = li.get('UnitAmount')
    account = li.get('AccountCode')
    tax = li.get('TaxType') or 'none'

    # Quantity/amount breakdown from extraction totals if present
    line_ex = ex.get('line_items', [])
    ex_li = line_ex[i] if i < len(line_ex) else {}

    li_summaries.append((desc, qty, unit, account, tax, ex_li))

line_items_text = []
for desc, qty, unit, account, tax, ex_li in li_summaries:
    clean_desc = (desc or '').strip()
    if len(clean_desc) > 90:
        clean_desc = clean_desc[:90] + '…'
    # Extract net and tax per line when available
    net = ex_li.get('amount_ex_vat') or ex_li.get('line_total')
    vat_amount = ex_li.get('vat_amount')

    # Format tax label like TAX001 (21%) when possible
    tax_type = tax
    tax_rate = ex_li.get('vat_rate') or ex_li.get('tax_rate')
    if isinstance(tax_rate, (int, float)) and tax_type != 'none':
        tax_label = f"{tax_type} ({int(round(tax_rate * 100))}%)"
    elif tax_type != 'none':
        tax_label = f"{tax_type}"
    else:
        tax_label = 'none'

    line_items_text.append(
        f"- {clean_desc} (line)\n"
        f"  Net: {('%.2f' % net) if isinstance(net,(int,float)) else '—'} {currency_ex}"
        f" • Account: {account} • Tax: {tax_label}"
    )

# Calculate totals from the payload line items — these are the exact numbers
# going to Xero, independent of whatever the extraction JSON contains.
subtotal_net = sum(
    li.get('UnitAmount', 0) * li.get('Quantity', 1)
    for li in line_items
    if isinstance(li.get('UnitAmount'), (int, float))
)
vat_total = sum(
    li.get('TaxAmount', 0)
    for li in line_items
    if isinstance(li.get('TaxAmount'), (int, float))
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
