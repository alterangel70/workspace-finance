#!/usr/bin/env python3
"""
Lobster step 3: merge workflow_inputs.json (from disk) with xero_data (from stdin).

Lobster steps can only pipe one prior step's stdout into stdin, so we need this
combiner: step 1 writes its output to disk, step 2 fetches Xero data, and this
step joins them both into a single context blob for the llm-task payload step.

stdin:  stdout of fetch_xero_data.sh  -- { contacts, accounts, tax_rates }
disk:   case_dir/workflow_inputs.json  -- { extraction, vendor_memory }
stdout: merged context for llm-task   -- { extraction, vendor_memory, xero_data }
"""
import argparse
import json
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
args = parser.parse_args()

case_dir = pathlib.Path(args.case_dir)

try:
    xero_data = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"ERROR: invalid JSON from fetch_xero_data.sh: {e}", file=sys.stderr)
    sys.exit(1)

inputs_file = case_dir / 'workflow_inputs.json'
if not inputs_file.exists():
    print(f"ERROR: workflow_inputs.json not found in {case_dir}", file=sys.stderr)
    sys.exit(1)

try:
    workflow_inputs = json.loads(inputs_file.read_text())
except json.JSONDecodeError as e:
    print(f"ERROR: workflow_inputs.json is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

result = {
    "extraction": workflow_inputs["extraction"],
    "vendor_memory": workflow_inputs.get("vendor_memory", {}),
    "xero_data": xero_data,
}

# Save a {TaxType: rate_fraction} lookup to disk so validate_payload.py can
# calculate approximate tax amounts for the approval preview without re-fetching.
tax_rates_lookup = {}
for tr in xero_data.get('tax_rates', []):
    tax_type = tr.get('TaxType') or tr.get('tax_type')
    # EffectiveRate is a percentage (e.g. 18.0 = 18%); handle both naming styles
    rate = (tr.get('EffectiveRate') or tr.get('effective_rate')
            or tr.get('DisplayTaxRate') or tr.get('display_tax_rate'))
    if tax_type and isinstance(rate, (int, float)):
        tax_rates_lookup[tax_type] = rate / 100.0
(case_dir / 'xero-rates.json').write_text(json.dumps(tax_rates_lookup))

print(json.dumps(result))
