name: invoice_to_xero_submit

# Called by the agent after the user approves the invoice preview returned
# by invoice_to_xero_prepare. All four args are required.
args:
  case_dir:
  supplier_name:
  supplier_slug:
  invoice_number:

steps:
  # Step 0: re-check Xero connection before writing anything to Xero.
  # The prepare workflow may have run minutes or hours ago; the 30-min access
  # token may have expired while the agent was waiting for user approval.
  # This step auto-refreshes the token before create_draft runs.
  - id: check_xero_connection
    command: bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/check_xero_connection.sh xero-default

  # Step 1: create the Xero DRAFT invoice.
  - id: create_draft
    command: bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/create_xero_draft.sh --json-file "${case_dir}/xero-payload.json" --idempotency-key "${invoice_number}"

  # Step 2: update vendor memory with any new contactId / accountCodes.
  - id: update_vendor_memory
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/update_vendor_memory.py --case-dir "${case_dir}" --supplier-slug "${supplier_slug}"
