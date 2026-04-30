name: invoice_to_xero_submit

# Args are passed via argsJson when invoking this workflow.
# All four are required; the workflow will fail early if scripts cannot find
# the expected files derived from these values.
args:
  case_dir:
  supplier_name:
  supplier_slug:
  invoice_number:

steps:
  # Step 1: read extraction.json + vendor memory, write workflow_inputs.json to
  # disk (so combine_context.py can access it later alongside xero data).
  - id: read_inputs
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/read_workflow_inputs.py --case-dir "${case_dir}" --supplier-slug "${supplier_slug}"

  # Step 2: fetch Xero contacts, accounts, and tax rates in one call.
  # Always runs (GET, idempotent). llm-task decides which data to use.
  - id: fetch_xero
    command: bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/fetch_xero_data.sh --search "${supplier_name}"

  # Step 3: merge workflow_inputs.json (disk) + xero data (stdin) into one
  # context blob. This is the workaround for Lobster's single-stdin-per-step
  # constraint: step 1 writes to disk, step 2 produces xero data, this step
  # joins them both.
  - id: combine_context
    stdin: $fetch_xero.stdout
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/combine_context.py --case-dir "${case_dir}"

  # Step 4: llm-task — evaluate vendor memory and build the complete xero-payload.
  # Receives the full context (extraction + vendor_memory + xero_data) via stdin.
  # Schema enforces all required Xero fields. No ContactID/AccountCode/TaxType
  # is ever invented — the model must select only from values present in the input.
  - id: build_payload
    stdin: $combine_context.stdout
    env:
      OPENCLAW_URL: "http://127.0.0.1:18789"
    pipeline: |-
      llm_task.invoke --args-json '{"prompt":"You receive a JSON object with three fields: extraction (all invoice data), vendor_memory (historical supplier data, may be {}), and xero_data (contacts, accounts, tax_rates from Xero). Build a complete Xero ACCPAY draft invoice payload. Rules: (1) Type must be the string ACCPAY. (2) Contact.ContactID: if vendor_memory.contactId is a non-null non-empty string use it exactly; otherwise find the best contact in xero_data.contacts by name similarity to extraction.supplier_name and use that ContactID. Never invent a ContactID. (3) AccountCode for each line item: if vendor_memory.accountCodes has entries suitable for the line item type prefer those codes; otherwise pick the most relevant account from xero_data.accounts. Never invent an AccountCode. (4) TaxType: if vendor_memory.taxTypes has suitable entries prefer those; otherwise pick from xero_data.tax_rates. Use empty string if no tax applies to a line item. (5) Date must be a YYYY-MM-DD string from extraction. DueDate must be a YYYY-MM-DD string if present in extraction, or null if not found. (6) Amounts and quantities must be numbers. (7) CurrencyCode must be the ISO 4217 code from extraction. (8) Reference must equal the invoice number from extraction if present. (9) Do not invent any ID, code, or type not present in the input data.","thinking":"low","schema":{"type":"object","properties":{"Type":{"type":"string"},"Contact":{"type":"object","properties":{"ContactID":{"type":"string"}},"required":["ContactID"],"additionalProperties":false},"Date":{"type":"string"},"DueDate":{"type":["string","null"]},"InvoiceNumber":{"type":"string"},"Reference":{"type":"string"},"CurrencyCode":{"type":"string"},"LineItems":{"type":"array","items":{"type":"object","properties":{"Description":{"type":"string"},"Quantity":{"type":"number"},"UnitAmount":{"type":"number"},"AccountCode":{"type":"string"},"TaxType":{"type":"string"}},"required":["Description","Quantity","UnitAmount","AccountCode"],"additionalProperties":false},"minItems":1}},"required":["Type","Contact","Date","CurrencyCode","LineItems"],"additionalProperties":false}}'

  # Step 5: save the llm-task output to case_dir/xero-payload.json.
  - id: save_payload
    stdin: $build_payload.stdout
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/save_payload.py --case-dir "${case_dir}"

  # Step 6: validate xero-payload.json deterministically.
  # Exit 1 here hard-stops the workflow before the approval gate.
  # stdout becomes the approval preview shown to the user.
  - id: validate
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/validate_payload.py --case-dir "${case_dir}"

  # Step 7: approval gate — workflow pauses here.
  # Lobster returns needs_approval + resumeToken.
  # The agent relays the validate summary to the user and asks for confirmation.
  # Resume with approve: true to proceed, approve: false to cancel.
  - id: approve
    stdin: $validate.stdout
    command: cat
    approval: required

  # Step 8: create the Xero DRAFT invoice. Only runs if approved.
  - id: create_draft
    command: bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/create_xero_draft.sh --json-file "${case_dir}/xero-payload.json" --idempotency-key "${invoice_number}"
    condition: $approve.approved

  # Step 9: update vendor memory. Only runs if approved AND draft was created.
  - id: update_vendor_memory
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/update_vendor_memory.py --case-dir "${case_dir}" --supplier-slug "${supplier_slug}"
    condition: $approve.approved
