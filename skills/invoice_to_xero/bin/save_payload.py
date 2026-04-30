#!/usr/bin/env python3
"""
Lobster step 5: save the xero-payload JSON produced by llm-task to disk.

stdin:  llm-task output  -- the raw xero-payload JSON object
stdout: confirmation envelope  -- { ok, saved_to }
"""
import argparse
import json
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--case-dir', required=True)
args = parser.parse_args()

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"ERROR: llm-task returned invalid JSON: {e}", file=sys.stderr)
    sys.exit(1)

out_file = pathlib.Path(args.case_dir) / 'xero-payload.json'
out_file.write_text(json.dumps(payload, indent=2))

print(json.dumps({"ok": True, "saved_to": str(out_file)}))
