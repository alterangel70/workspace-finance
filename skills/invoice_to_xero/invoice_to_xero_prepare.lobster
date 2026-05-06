name: invoice_to_xero_prepare

# Args are passed via argsJson when invoking this workflow.
# All four are required; the workflow will fail early if scripts cannot find
# the expected files derived from these values.
args:
  case_dir:
  supplier_name:
  supplier_slug:
  invoice_number:

steps:
  # Step 0: verify the Xero connection is valid before doing any work.
  # Exits immediately with a clear message if the token is expired or missing,
  # instead of failing obscurely inside fetch_xero with "curl failed".
  - id: check_xero_connection
    command: bash /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/check_xero_connection.sh xero-default

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

  # Step 4: call llm-task via HTTP, passing the combined context as `input`.
  # Using a command: script instead of run: openclaw.invoke because the Lobster
  # pipeline openclaw.invoke command drains and discards stdin before calling the
  # API, so the LLM would receive INPUT_JSON: null. The script reads stdin and
  # includes it as the `input` field in the API args.
  - id: build_payload
    stdin: $combine_context.stdout
    env:
      OPENCLAW_URL: "http://127.0.0.1:18789"
      OPENCLAW_TOKEN: "c2c9574f01b26bb4a69e99a3f86860d004ca665cc07a8845"
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/build_xero_payload.py

  # Step 5: save the llm-task output to case_dir/xero-payload.json.
  - id: save_payload
    stdin: $build_payload.stdout
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/save_payload.py --case-dir "${case_dir}"

  # Step 6: validate xero-payload.json deterministically and emit the
  # human-readable approval preview as JSON: {"ok": true, "preview": "..."}.
  # Exit 1 here hard-stops the workflow before the agent asks for approval.
  # The agent reads output[-1]["preview"] and displays it to the user.
  - id: validate
    command: python3 /home/ao/.openclaw/workspace-finance/skills/invoice_to_xero/bin/validate_payload.py --case-dir "${case_dir}"
