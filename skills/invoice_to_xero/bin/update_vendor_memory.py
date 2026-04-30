#!/usr/bin/env python3
"""
Lobster step 9 (post-approval): update vendor memory after a successful Xero draft.

Implements the deterministic logic from SKILL.md step 19 (original):
- creates vendor file if missing
- updates contactId, currency, usageCount, lastUsed
- merges accountCodes and taxTypes with per-entry useCount

Only runs when condition: $approve.approved is true (handled by Lobster).
"""
import argparse
import datetime
import json
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
parser.add_argument('--supplier-slug', required=True)
args = parser.parse_args()

case_dir = pathlib.Path(args.case_dir)
extraction_file = case_dir / 'extraction.json'
payload_file = case_dir / 'xero-payload.json'

for f in (extraction_file, payload_file):
    if not f.exists():
        print(f"ERROR: {f.name} not found in {case_dir}", file=sys.stderr)
        sys.exit(1)

extraction = json.loads(extraction_file.read_text())
payload = json.loads(payload_file.read_text())

# Vendors dir: .../data/vendors/ (three levels up from case_dir)
vendors_dir = case_dir.parent.parent.parent / 'vendors'
vendors_dir.mkdir(parents=True, exist_ok=True)
vendor_file = vendors_dir / f"{args.supplier_slug}.json"

if vendor_file.exists():
    memory = json.loads(vendor_file.read_text())
else:
    memory = {
        "slug": args.supplier_slug,
        "name": extraction.get("supplier_name", args.supplier_slug),
        "contactId": None,
        "currency": payload.get("CurrencyCode", "EUR"),
        "usageCount": 0,
        "lastUsed": None,
        "accountCodes": [],
        "taxTypes": [],
    }

# Update contact
contact_id = payload.get("Contact", {}).get("ContactID")
if contact_id:
    memory["contactId"] = contact_id

# Update currency
if payload.get("CurrencyCode"):
    memory["currency"] = payload["CurrencyCode"]

# Increment usage
memory["usageCount"] = memory.get("usageCount", 0) + 1
memory["lastUsed"] = datetime.date.today().isoformat()

# Merge accountCodes
for li in payload.get("LineItems", []):
    code = str(li.get("AccountCode", "")).strip()
    if not code:
        continue
    existing = next((a for a in memory["accountCodes"] if a["code"] == code), None)
    if existing:
        existing["useCount"] = existing.get("useCount", 0) + 1
    else:
        memory["accountCodes"].append({
            "code": code,
            "description": li.get("Description", "")[:60],
            "useCount": 1,
        })

# Merge taxTypes
seen_tax = set()
for li in payload.get("LineItems", []):
    tax_type = str(li.get("TaxType", "")).strip()
    if not tax_type or tax_type in seen_tax:
        continue
    seen_tax.add(tax_type)
    existing = next((t for t in memory["taxTypes"] if t["type"] == tax_type), None)
    if existing:
        existing["useCount"] = existing.get("useCount", 0) + 1
    else:
        memory["taxTypes"].append({
            "type": tax_type,
            "name": tax_type,
            "useCount": 1,
        })

vendor_file.write_text(json.dumps(memory, indent=2))
print(json.dumps({
    "ok": True,
    "updated": str(vendor_file),
    "usageCount": memory["usageCount"],
}))
