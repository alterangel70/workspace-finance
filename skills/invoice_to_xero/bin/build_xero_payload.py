#!/usr/bin/env python3
"""
Lobster step 4: call llm-task via OpenClaw HTTP API, passing the combined
context as the `input` field so the LLM actually receives extraction +
vendor_memory + xero_data.

Previously this step used `openclaw.invoke` as a Lobster pipeline `run:`
command, which drained and discarded stdin before calling the API — meaning
the LLM always received `INPUT_JSON: null`.

stdin:  combined context  -- { extraction, vendor_memory, xero_data }
stdout: xero-payload JSON object
"""
import json
import os
import sys
import urllib.request
import urllib.error

try:
    combined_context = json.load(sys.stdin)
except json.JSONDecodeError as e:
    print(f"ERROR: invalid JSON from combine_context: {e}", file=sys.stderr)
    sys.exit(1)

OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://127.0.0.1:18789")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "")

PROMPT = (
    "You receive a JSON object with three fields: extraction (all invoice data), "
    "vendor_memory (historical supplier data, may be {}), and xero_data (contacts, "
    "accounts, tax_rates from Xero). Build a complete Xero ACCPAY draft invoice "
    "payload. Rules: "
    "(1) Type must be the string ACCPAY. "
    "(2) Contact.ContactID: if vendor_memory.contactId is a non-null non-empty string "
    "use it exactly; otherwise find the best contact in xero_data.contacts by name "
    "similarity to extraction.supplier_name and use that ContactID. Never invent a ContactID. "
    "(3) AccountCode for each line item: if vendor_memory.accountCodes has entries "
    "suitable for the line item type prefer those codes; otherwise pick the most "
    "relevant account from xero_data.accounts. Never invent an AccountCode. "
    "(4) TaxType: if vendor_memory.taxTypes has suitable entries prefer those; otherwise "
    "pick from xero_data.tax_rates. Use empty string if no tax applies to a line item. "
    "(5) Date must be a YYYY-MM-DD string from extraction. DueDate must be a YYYY-MM-DD "
    "string if present in extraction, or null if not found. "
    "(6) Amounts and quantities must be numbers. "
    "(7) CurrencyCode must be the ISO 4217 code from extraction. "
    "(8) Reference must equal the invoice number from extraction if present. "
    "(9) Do not invent any ID, code, or type not present in the input data."
)

# NOTE: Keep the schema intentionally permissive.
# The strict schema here has been observed to trigger llm-task HTTP 500.
# We still validate the presence of core top-level fields, but we avoid
# over-constraining nested objects.
SCHEMA = {
    # Very permissive schema to avoid llm-task HTTP 500 on over-constrained
    # nested structures.
    "type": "object",
    "properties": {
        "Type": {"type": "string"},
        "Contact": {"type": "object"},
        "Date": {"type": "string"},
        "DueDate": {},
        "InvoiceNumber": {},
        "Reference": {},
        "CurrencyCode": {"type": "string"},
        "LineItems": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "object"},
        },
    },
    "required": ["Type", "Contact", "Date", "CurrencyCode", "LineItems"],
}

payload = {
    "tool": "llm-task",
    "action": "json",
    "args": {
        "prompt": PROMPT,
        "input": combined_context,
        "schema": SCHEMA,
    },
}

headers = {"content-type": "application/json"}
if OPENCLAW_TOKEN:
    headers["authorization"] = f"Bearer {OPENCLAW_TOKEN}"

req = urllib.request.Request(
    f"{OPENCLAW_URL}/tools/invoke",
    data=json.dumps(payload).encode(),
    headers=headers,
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        response_text = resp.read().decode()
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"ERROR: llm-task HTTP {e.code}: {body[:400]}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: llm-task request failed: {e}", file=sys.stderr)
    sys.exit(1)

try:
    response = json.loads(response_text)
except json.JSONDecodeError as e:
    print(f"ERROR: invalid JSON response from OpenClaw: {e}", file=sys.stderr)
    sys.exit(1)

if not response.get("ok"):
    msg = response.get("error", {}).get("message", "Unknown error")
    print(f"ERROR: llm-task error: {msg}", file=sys.stderr)
    sys.exit(1)

result = response.get("result")
if result is None:
    print("ERROR: llm-task returned no result", file=sys.stderr)
    sys.exit(1)

# Extract the xero payload from the tool result.
# llm-task execute() returns:
#   { content: [{type:"text", text:"<json>"}], details: {json: <parsed>, ...} }
# The API wraps it as { ok: true, result: <execute_return> }.
xero_payload = None
if isinstance(result, dict):
    details = result.get("details")
    if isinstance(details, dict) and "json" in details:
        xero_payload = details["json"]
    elif "content" in result:
        content = result.get("content", [])
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            try:
                xero_payload = json.loads(text)
            except json.JSONDecodeError:
                pass

if xero_payload is None:
    # Fallback: maybe the API unwrapped and result IS the payload directly.
    xero_payload = result

print(json.dumps(xero_payload))
