---
name: invoice_to_xero
description: Extract an invoice, reuse vendor memory when possible, match to Xero when needed, build the final Xero payload, ask for confirmation, and create a Xero draft.
license: MIT
metadata:
  author: openclaw
  version: "2.0.0"
  requires:
    bins:
      - curl
      - python3
  primaryEnv: M365_XERO_API_KEY
allowed-tools: lobster
---

# invoice_to_xero

Use this skill when the user sends an invoice and asks to upload it to Xero.

## Rules

- Only create DRAFT invoices.
- Never authorise invoices.
- Never create a draft from raw extraction output.
- Never invent `ContactID`, `AccountCode`, or `TaxType`.
- Always run the Lobster workflow for everything after extraction.
- Never call `create_xero_draft.sh` directly — that is Lobster's job.

## Files

For each invoice case, create:

`<case_dir>` = `/home/ao/.openclaw/workspace-finance/data/invoices/pending/<case-id>/`

Agent writes:
- `source` — original invoice file
- `extraction.json` — extracted invoice data

Everything else under `<case_dir>` is written by the Lobster workflow.

## File path handling

If the user provides a valid absolute path or file:// URL for the invoice file:
- treat that path as canonical for the whole workflow
- reuse that exact path in all later steps
- do not rewrite it as a relative path

If extraction succeeds once from that path, do not run extraction again.
Use the extracted result already obtained and continue to the Lobster handoff.

## Extraction reuse

If the invoice was already extracted successfully in the current turn or current case:
- do not re-extract it
- save the result to `extraction.json`
- proceed directly to the Lobster handoff

## Agent steps (before Lobster)

**Step 1.** Make sure the invoice file exists locally. If the current message includes a PDF attachment, download it and use that as the source file. If the message references an invoice file path, check that it exists locally. If the file is missing or inaccessible, stop and inform the user.

**Step 2.** Create `<case_dir>`:
```
/home/ao/.openclaw/workspace-finance/data/invoices/pending/<case-id>/
```
Use the invoice number as `<case-id>` if available, otherwise derive one from the filename.

**Step 3.** Save the original file to `<case_dir>/source`.

**Step 4.** Extract the invoice using the built-in `pdf` tool with this prompt:

> You are an invoice data extractor. Extract ALL visible invoice fields as JSON: invoice number, date, due date, supplier name, buyer name, line items, amounts, taxes, totals, currency, IBAN, and reference. Return ONLY valid JSON.
> 
> The SUPPLIER is the external vendor who issued this invoice — the party we are paying. The BUYER is the company receiving the invoice (our own company). Never set supplier_name to our own company name (Valletta Credit Finance Corporation Limited or any variant).

Save the result to `<case_dir>/extraction.json`.

Hard-stop here if:
- extraction fails
- `extraction.json` cannot be written
- `supplier_name` is missing from the extracted data
- `supplier_name` matches our own company name or a known variant ("Valletta Credit Finance Corporation Limited", "Valletta Credit Finance", "VCF", "Valletta Credit Finance Corp") — this means buyer and supplier were swapped; ask the user to confirm the correct supplier before proceeding

## Lobster handoff (step 5)

After saving `extraction.json`, build the `supplier-slug` from the supplier name:
- lowercase the name
- replace any sequence of non-alphanumeric characters with a single hyphen
- strip leading and trailing hyphens
- example: `"Camilleri Preziosi Advocates"` → `"camilleri-preziosi-advocates"`

Call the `lobster` tool — do not use Bash for this step:

```json
{
  "action": "run",
  "pipeline": "/home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/invoice_to_xero_submit.lobster",
  "argsJson": "{\"case_dir\": \"<case_dir>\", \"supplier_name\": \"<supplier_name>\", \"supplier_slug\": \"<supplier_slug>\", \"invoice_number\": \"<invoice_number>\"}",
  "timeoutMs": 60000
}
```

Replace `<case_dir>`, `<supplier_name>`, `<supplier_slug>`, and `<invoice_number>` with the actual values from `extraction.json`. The workflow runs entirely inside the Lobster engine and will pause at an approval gate.

## Handling the approval gate

⛔ **STOP. When Lobster returns `needs_approval`, do NOT call lobster again. Do NOT read extraction.json again. Do NOT do anything else.**

The only permitted actions at this point are:

1. Read `<case_dir>/approval-preview.txt` — display its full contents verbatim in the chat, exactly as-is.
2. Ask the user: "Approve this invoice? (yes / no)"
3. Wait for the user's reply in the current session.
4. Delete `<case_dir>/approval-preview.txt`.
5. Call lobster with `resume` and the `resumeToken` received above.

If the user confirms:
```json
{ "action": "resume", "token": "<resumeToken>", "approve": true }
```

If the user denies:
```json
{ "action": "resume", "token": "<resumeToken>", "approve": false }
```

**If you already have a `resumeToken` from a previous lobster call in this session**: do not call lobster with `run` again. Use the existing `resumeToken` to resume.

**If `approval-preview.txt` does not exist**: display the contents of `<case_dir>/xero-payload.json` as a fallback summary instead.

## Hard stops

Stop before invoking Lobster if:
- the invoice file is missing
- extraction fails
- `supplier_name` is missing from `extraction.json`
- `invoice_number` is missing from `extraction.json`

Stop and report error if Lobster returns a non-ok status.
Do not silently retry financial write operations.

## Errors

Classify the failure before responding:

| Category | Examples | What to do |
|---|---|---|
| **Recoverable (auto-retry once)** | `llm-task` timeout or transient HTTP 5xx from proxy | Retry the Lobster call once silently. If it fails again, escalate as below. |
| **Requires user action** | `check_xero_connection` fails with `expired`/`missing` · `validate` step rejects payload · contact not found in Xero · approval denied by user | Stop immediately. Report the exact error. Explain what the user must do to unblock (e.g. re-authorise Xero, fix the invoice data, or correct the contact). |
| **Hard stop — do not retry** | `supplier_name` missing from `extraction.json` · `invoice_number` missing · `extraction.json` unreadable · `read_inputs` exits non-zero | Stop. Report which field is missing and from which file. Do not attempt the Lobster call. |

For all failures:
- state which step failed (Lobster reports the step id)
- quote the exact error message
- do not silently retry financial write operations (step `create_draft` and beyond)

