---
name: invoice_to_xero
description: Extract an invoice, reuse vendor memory when possible, match to Xero when needed, build the final Xero payload, ask for confirmation, and create a Xero draft.
license: MIT
metadata:
  author: openclaw
  version: "1.0.0"
  requires:
    bins:
      - curl
      - python3
  primaryEnv: M365_XERO_API_KEY
allowed-tools: Bash(bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/*.sh)
---

# invoice_to_xero

Use this skill when the user sends an invoice and asks to upload it to Xero.

## Rules

- Only create DRAFT invoices.
- Never authorise invoices.
- Never create a draft from raw extraction output.
- Always build `xero-payload.json` first.
- Always ask the user for confirmation before calling `create_xero_draft.sh`.
- Never invent `ContactID`, `AccountCode`, or `TaxType`.

## Files

For each invoice case, create:

<case_dir> = /home/ao/.openclaw/workspace-finance/data/invoices/pending/<case-id>/

Inside that folder:

- source
- extraction.json
- xero-payload.json

Vendor memory file (one per supplier):

`/home/ao/.openclaw/workspace-finance/data/vendors/<supplier-slug>.json`

Schema:
```json
{
  "slug": "<supplier-slug>",
  "name": "<supplier name as extracted>",
  "contactId": "<xero contact uuid>",
  "currency": "EUR",
  "usageCount": 0,
  "lastUsed": "YYYY-MM-DD",
  "accountCodes": [
    { "code": "431", "description": "...", "useCount": 1 }
  ],
  "taxTypes": [
    { "type": "TAX002", "name": "IVA 21%", "useCount": 1 }
  ]
}
```

## File path handling

If the user provides a valid absolute path or file:// URL for the invoice file:
- treat that path as canonical for the whole workflow
- reuse that exact path in all later steps
- do not rewrite it as a relative path
- do not replace it with data/... or any other inferred path

If extraction succeeds once from that path, do not run extraction again on a rewritten path.
Use the extracted result already obtained and continue with matching and payload creation.


## Extraction reuse

If the invoice was already extracted successfully in the current turn or current case:
- do not re-extract it
- save the result to extraction.json
- continue directly to vendor memory / Xero matching / payload generation


## Steps

1. Make sure the invoice file exists locally, If the current message includes a PDF attachment, download it and use that as the source file. If the message does not include an attachment but references an invoice file, check that the file exists locally and is accessible. If the file is missing or inaccessible, stop and inform the user.
2. Create `<case_dir>`.
3. Save the original file in `<case_dir>/source`.
4. If the file is a PDF, use the built-in `pdf` tool with this prompt:

You are an invoice data extractor. Extract ALL visible invoice fields as JSON: invoice number, date, due date, supplier name, buyer name, line items, amounts, taxes, totals, currency, IBAN, and reference. Return ONLY valid JSON.

5. Save the result to `<case_dir>/extraction.json`.
6. Read supplier name from `extraction.json`.
7. Build `<supplier-slug>` from the supplier name.
8. Check whether this file exists:

`/home/ao/.openclaw/workspace-finance/data/vendors/<supplier-slug>.json`

9. If vendor memory exists, evaluate it before querying Xero:
- Review `accountCodes` and `taxTypes` entries against this specific invoice
- If they look correct for the invoice, use them
- If they look wrong or insufficient for the invoice, ignore them and fall through to the Xero lookup
- Always use `contactId` from memory if present (do not re-search a known contact)

10. Skip the Xero lookup if vendor memory contains a confirmed `contactId` and the AI judges the account codes and tax types are appropriate for this invoice.

11. If vendor memory is missing, incomplete, or the AI judges it unsuitable, run:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/fetch_xero_data.sh --search "<supplier_name>"

12. If that does not return a reliable contact, run:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/fetch_xero_data.sh

13. From the available data, choose:
- the best Xero contact
- the best account code for each line item
- the best tax type for each taxed line

14. Build the final Xero payload and save it to:

<case_dir>/xero-payload.json

15. The payload must contain at least:
- Type = ACCPAY
- Contact.ContactID
- Date
- InvoiceNumber or Reference (Reference has to be equal to the invoice number)
- CurrencyCode
- LineItems

Xero payload field rules:

Top-level fields:
- `Type`: string
- `Contact.ContactID`: string UUID
- `Date`: string in `YYYY-MM-DD`
- `DueDate`: string in `YYYY-MM-DD` if present
- `InvoiceNumber`: string if present
- `Reference`: string if present
- `CurrencyCode`: string ISO currency code such as `EUR`, `USD`, `GBP`
- `LineItems`: array with one or more objects

Each `LineItems` entry must follow these rules:
- `Description`: string
- `Quantity`: number
- `UnitAmount`: number
- `AccountCode`: string
- `TaxType`: string when tax applies

Validation rules:
- never write `null` for required fields
- never write text where a number is required
- never write text where an object or array is required
- never write placeholders
- never omit `LineItems`
- never omit `Contact.ContactID`
- never use non-ISO currency values
- always format dates as `YYYY-MM-DD`
- always use numeric values for amounts and quantities
- if a quantity is not explicitly known, use a numeric default that keeps the line mathematically valid
- the payload must be valid JSON

16. Show the user a short and readable summary:
- supplier
- matched contact
- invoice number
- date
- due date
- currency
- line items
- account codes
- tax types
- subtotal
- tax
- total

17. Ask the user to confirm draft creation.
18. Only after confirmation, run:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/create_xero_draft.sh --json-file "<case_dir>/xero-payload.json" --idempotency-key "<invoice-number>"

19. If the draft is created successfully, update vendor memory at `/home/ao/.openclaw/workspace-finance/data/vendors/<supplier-slug>.json`:
- If the file does not exist, create it using the schema above
- Set `contactId` from the contact used
- Set `currency` from the invoice
- Increment top-level `usageCount` by 1
- Set `lastUsed` to today's date (YYYY-MM-DD)
- For each `accountCode` used: if it exists in `accountCodes`, increment its `useCount` by 1; otherwise append it with `useCount: 1`
- For each `taxType` used: if it exists in `taxTypes`, increment its `useCount` by 1; otherwise append it with `useCount: 1`

## Vendor memory rules

Always check vendor memory before running a Xero lookup.

Vendor memory is valid to use when:
- it contains a confirmed `contactId`
- the AI judges that the `accountCodes` and `taxTypes` entries are appropriate for the current invoice
- it does not contradict the extracted invoice data

If any of those is false, fall back to Xero. Still reuse `contactId` from memory if present — do not re-search a contact you already know.

Always update vendor memory after a successful draft, whether memory was used or not. This is how the agent learns.

Do not store guesses. Only write to vendor memory after a draft has been confirmed and successfully created.

## Commands

Health check:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/health_check.sh

Primary lookup:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/fetch_xero_data.sh --search "<supplier_name>"

Fallback lookup:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/fetch_xero_data.sh

Create draft:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/create_xero_draft.sh --json-file "<case_dir>/xero-payload.json" --idempotency-key "<invoice-number>"

Void only if the user explicitly asks:

bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/void_xero_invoice.sh --invoice-id "<uuid>"

Optional debugging scripts:
- list_xero_contacts.sh
- list_xero_accounts.sh
- list_xero_tax_rates.sh

## Hard stops

Stop and do not create a draft if:
- the invoice file is missing
- extraction fails
- supplier name is missing
- no reliable Xero contact match exists
- ContactID is missing
- invoice number or reference is missing
- line items are missing
- an account code is missing or uncertain
- a tax type is missing where tax applies
- totals, currency, or dates do not make sense
- `xero-payload.json` does not exist
- the user has not confirmed the draft

## Errors

If a script fails:
- say which script failed
- say the exact error
- stop

Do not silently retry financial write operations.
