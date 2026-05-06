#!/usr/bin/env python3
"""Scan a mailbox fetch JSON output for likely invoice emails and persist pending items.

Reads JSON output from fetch_mail.py on stdin.
Filters messages by heuristic scoring (subject keywords + attachment types).
Writes one JSON file per new candidate to --incoming-dir.
Saves attachment bytes to disk when present in the fetch payload.
Prints a JSON summary to stdout.

Usage (via Lobster pipeline / stdin):
    python3 scripts/fetch_mail.py --config config.yaml | \\
        python3 skills/mailbox_invoice_watch/bin/scan_inbox.py \\
            --incoming-dir /path/to/data/mailbox/pending

Usage (standalone with --help):
    python3 scan_inbox.py --help
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

# Subject keywords that strongly suggest an invoice-related email.
# All matched case-insensitively against the full subject string.
SUBJECT_KEYWORDS: list[str] = [
    "invoice",
    "factura",
    "rechnung",
    "fattura",
    "facture",
    "tax invoice",
    "proforma",
    "pro-forma",
    "bill",
    "receipt",
    "statement",
    "quotation",
    "quote",
    "purchase order",
    "po #",
    "po#",
    "remittance",
    "credit note",
    "payment advice",
]

# Attachment MIME types that typically carry invoice documents.
INVOICE_ATTACHMENT_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",   # generic – still worth catching if extension matches
})

# File extensions (lower-case) that suggest an invoice document.
INVOICE_ATTACHMENT_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
})


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def compute_pending_id(message_id: str) -> str:
    """Return a stable, filesystem-safe pending-item ID derived from message_id.

    Format: ``inv-<16 hex chars>``
    """
    raw = (message_id or "").strip()
    if not raw:
        raise ValueError("message_id is empty — cannot compute stable pending ID")
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"inv-{digest}"


def score_message(msg: dict) -> int:
    """Score a message for invoice likelihood.

    Scoring:
        +2  subject matches at least one invoice keyword
        +1  has at least one attachment with an invoice MIME type or extension

    Returns:
        int score (0 = skip, ≥1 = candidate)
    """
    score = 0

    subject = (msg.get("subject") or "").lower()
    for kw in SUBJECT_KEYWORDS:
        if kw in subject:
            score += 2
            break

    for att in (msg.get("attachments") or []):
        ct = (att.get("content_type") or "").lower().split(";")[0].strip()
        fname = att.get("filename") or ""
        ext = Path(fname).suffix.lower() if fname else ""
        if ct in INVOICE_ATTACHMENT_TYPES or ext in INVOICE_ATTACHMENT_EXTENSIONS:
            score += 1
            break

    return score


def _strip_html(html: str) -> str:
    """Very lightweight HTML tag stripper for body summaries (no external deps)."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe version of an attachment filename."""
    safe = re.sub(r"[^\w.\- ]", "_", name).strip()
    return safe or "attachment"


def save_attachments(msg: dict, case_dir: Path) -> list[dict]:
    """Save attachment files that carry base64 data to ``case_dir/attachments/``.

    Returns a list of attachment-info dicts, each with:
        filename, content_type, size, saved_path (str or None)
    """
    attachments = msg.get("attachments") or []
    if not attachments:
        return []

    att_dir = case_dir / "attachments"
    result: list[dict] = []

    for att in attachments:
        filename = att.get("filename") or "attachment"
        content_type = att.get("content_type") or "application/octet-stream"
        size = att.get("size") or 0
        data_b64 = att.get("data_b64") or ""
        saved_path = None

        if data_b64:
            att_dir.mkdir(parents=True, exist_ok=True)
            safe_name = _safe_filename(filename)
            dest = att_dir / safe_name
            # Avoid overwriting: append numeric suffix if needed
            if dest.exists():
                stem = Path(safe_name).stem
                suffix = Path(safe_name).suffix
                counter = 1
                while dest.exists():
                    dest = att_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            try:
                dest.write_bytes(base64.b64decode(data_b64))
                saved_path = str(dest)
            except Exception as exc:
                print(
                    f"Warning: could not save attachment '{filename}': {exc}",
                    file=sys.stderr,
                )

        result.append({
            "filename": filename,
            "content_type": content_type,
            "size": size,
            "saved_path": saved_path,
        })

    return result


def build_pending_item(
    msg: dict,
    pending_id: str,
    score: int,
    attachment_info: list[dict],
    fetch_account: str,
) -> dict:
    """Build the pending-item dict to be persisted as JSON."""
    sender = msg.get("sender") or {}
    if isinstance(sender, dict):
        sender_address = sender.get("address") or ""
        sender_name = sender.get("display_name") or ""
    else:
        sender_address = str(sender)
        sender_name = ""

    body_plain = (msg.get("body_plain") or "").strip()
    if not body_plain:
        body_plain = _strip_html(msg.get("body_html") or "")
    body_summary = body_plain[:500]

    account = msg.get("account") or fetch_account or ""
    mailbox = msg.get("mailbox") or "INBOX"
    now = datetime.now(timezone.utc).isoformat()

    return {
        "id": pending_id,
        "message_id": msg.get("message_id") or "",
        "account": account,
        "mailbox": mailbox,
        "subject": msg.get("subject") or "",
        "sender_address": sender_address,
        "sender_name": sender_name,
        "date": msg.get("date") or None,
        "body_summary": body_summary,
        "attachment_info": attachment_info,
        "status": "pending",
        "scan_score": score,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan mailbox fetch output for invoice candidates"
    )
    parser.add_argument(
        "--incoming-dir",
        required=True,
        help="Directory to store pending invoice items (one JSON file per item)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=1,
        help="Minimum score to consider a message a candidate (default: 1)",
    )
    args = parser.parse_args()

    incoming_dir = Path(args.incoming_dir)
    incoming_dir.mkdir(parents=True, exist_ok=True)

    # Read fetch_mail.py JSON output from stdin
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        _fatal(f"Failed to parse JSON from stdin: {exc}")

    if isinstance(data, list):
        fetch_account = ""
        messages: list[dict] = data
    elif isinstance(data, dict):
        fetch_account = data.get("account") or ""
        messages = data.get("messages") or []
    else:
        _fatal(f"Unexpected input type: {type(data).__name__}")

    total_scanned = len(messages)
    new_items: list[dict] = []
    skipped_known = 0
    skipped_low_score = 0

    for msg in messages:
        message_id = (msg.get("message_id") or "").strip()
        if not message_id:
            skipped_low_score += 1
            continue

        score = score_message(msg)
        if score < args.min_score:
            skipped_low_score += 1
            continue

        try:
            pending_id = compute_pending_id(message_id)
        except ValueError as exc:
            print(f"Warning: skipping message — {exc}", file=sys.stderr)
            skipped_low_score += 1
            continue

        # Skip if this message was already recorded in a previous scan
        item_path = incoming_dir / f"{pending_id}.json"
        if item_path.exists():
            skipped_known += 1
            continue

        # Save attachment files when byte data is present in the fetch payload
        case_dir = incoming_dir / pending_id
        attachment_info = save_attachments(msg, case_dir)

        # Build and persist the pending item
        item = build_pending_item(msg, pending_id, score, attachment_info, fetch_account)
        item_path.write_text(json.dumps(item, indent=2, default=str), encoding="utf-8")

        new_items.append({
            "id": pending_id,
            "subject": item["subject"],
            "sender_address": item["sender_address"],
            "date": item["date"],
            "score": score,
            "attachment_count": len(attachment_info),
            # Human-friendly display for cron notifications (avoid opaque inv- IDs)
            "attachment_filenames": [a.get("filename") for a in attachment_info if a.get("filename")],
            "display_attachment_filename": (attachment_info[0].get("filename") if attachment_info and attachment_info[0].get("filename") else ""),
        })

    summary = {
        "ok": True,
        "scanned": total_scanned,
        "new_candidates": len(new_items),
        "skipped_known": skipped_known,
        "skipped_low_score": skipped_low_score,
        "items": new_items,
    }
    json.dump(summary, sys.stdout, indent=2, default=str)
    print()


def _fatal(msg: str) -> None:
    json.dump({"error": msg}, sys.stderr, default=str)
    print(file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
