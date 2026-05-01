#!/usr/bin/env python3
"""
auto_invoice.py — Headless monthly invoice sender for PB&J Strategic Accounting.

Designed to be triggered by Windows Task Scheduler on the 1st of each month.
It will:
  1. Load all settings from the shared SQLite database.
  2. Use a saved email body draft if one exists for this invoice, otherwise
     call Claude Haiku to generate a personalised one and save it.
  3. Generate the invoice PDF.
  4. Send the email with the PDF attached via Gmail SMTP.
  5. Log the outcome to invoices/auto_invoice.log.

Usage
-----
  python auto_invoice.py                       # bill for current month
  python auto_invoice.py --month 2026-07       # bill for a specific month
  python auto_invoice.py --draft-only          # generate+save draft, don't send
  python auto_invoice.py --show-draft          # print the current draft and exit

The --draft-only flag is useful for running a few days early so you can open
the app, review/tweak the body in the Invoice dialog, then let the scheduler
handle the actual send on the 1st.
"""

import sys
import os
import argparse
import calendar
import logging
import smtplib
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

import database          # noqa: E402 — needs sys.path insert above
import invoice_pdf       # noqa: E402

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_PATH = APP_DIR / "invoices" / "auto_invoice.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _invoice_date(month_arg: str | None) -> date:
    """Return the 1st of the target month."""
    if month_arg:
        y, m = map(int, month_arg.split("-"))
        return date(y, m, 1)
    today = date.today()
    return date(today.year, today.month, 1)


def _invoice_email_template(settings: dict, inv_data: dict) -> str:
    """Standard invoice email body — same style every month, values filled in."""
    return (
        f"Dear {settings['company_name']},\n\n"
        f"Please find attached invoice {inv_data['invoice_number']} covering all "
        f"{inv_data['service_description']} for the month of {inv_data['period_label']}.\n\n"
        f"Invoice Date:    {inv_data['invoice_date']}\n"
        f"Service Period:  {inv_data['period_label']} (all work this month)\n"
        f"Amount Due:      ${settings['retainer_amount']}\n\n"
        f"Hours worked as of {inv_data['hours_as_of']} (informational):\n"
        f"  {inv_data['hours_in_period']:.1f} hrs in {inv_data['period_label']}"
        f"   |   {inv_data['hours_total']:.1f} hrs total on record\n\n"
        f"Please don't hesitate to reach out with any questions.\n\n"
        f"Best regards,\n{inv_data['your_name']}"
    )


def _smtp_send(gmail_user: str, app_password: str, to_email: str,
               subject: str, body: str, pdf_path: str) -> None:
    display_name = gmail_user.split("@")[0].replace(".", " ").title()
    msg = MIMEMultipart()
    msg["From"]       = formataddr((display_name, gmail_user))
    msg["To"]         = to_email
    msg["Subject"]    = subject
    msg["Date"]       = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=gmail_user.split("@")[1])
    msg["X-Mailer"]   = "Time Tracker — PB&J Strategic Accounting"
    msg.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition",
                    f'attachment; filename="{os.path.basename(pdf_path)}"')
    msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, to_email, msg.as_string())


# ── Main ──────────────────────────────────────────────────────────────────────

def run(month_arg: str | None = None,
        draft_only: bool = False,
        show_draft: bool = False) -> None:

    database.init_db()

    # Respect the auto-send toggle set in the Invoice dialog
    if not draft_only and not show_draft:
        if database.get_setting("auto_invoice_enabled", "1") != "1":
            log.info("Auto-send is disabled in the app (Invoice dialog toggle). "
                     "Exiting without sending. Re-enable it there to resume.")
            return

    inv_date  = _invoice_date(month_arg)
    inv_num   = f"INV-{inv_date.year}{inv_date.month:02d}"
    last_day  = calendar.monthrange(inv_date.year, inv_date.month)[1]
    p_start   = inv_date.replace(day=1).isoformat()
    p_end     = inv_date.replace(day=last_day).isoformat()
    today     = date.today()

    log.info("=== auto_invoice.py  target=%s ===", inv_num)

    settings = {
        "your_name":       database.get_setting("your_name",       "Consultant"),
        "company_name":    database.get_setting("company_name",    "Client"),
        "client_email":    database.get_setting("client_email",    ""),
        "retainer_amount": database.get_setting("retainer_amount", "750.00"),
        "venmo_username":  database.get_setting("venmo_username",  ""),
    }

    inv_data = {
        "your_name":           settings["your_name"],
        "invoice_number":      inv_num,
        "invoice_date":        inv_date.strftime("%B %d, %Y"),
        "period_label":        inv_date.strftime("%B %Y"),
        "period_start":        p_start,
        "period_end":          p_end,
        "service_description": database.get_setting(
            "invoice_service",
            "AI Integration & Web Development Services — Monthly Retainer"),
        "hours_as_of":         today.strftime("%B %d, %Y"),
        "hours_in_period":     database.get_hours_in_period(p_start, p_end),
        "hours_total":         database.get_total_hours_up_to(today.isoformat()),
    }

    # ── Email body: use saved draft or generate with AI ───────────────────────
    draft_key = f"email_draft_{inv_num}"
    body = database.get_setting(draft_key, "").strip()

    if not body:
        log.info("No saved draft for %s — generating from standard template…", inv_num)
        body = _invoice_email_template(settings, inv_data)
        database.set_setting(draft_key, body)
        log.info("Draft saved  (key: %s)", draft_key)
    else:
        log.info("Using saved draft from database  (key: %s)", draft_key)

    # ── --show-draft / --draft-only early exit ────────────────────────────────
    if show_draft or draft_only:
        print("\n" + "=" * 62)
        print(f"  DRAFT — {inv_num}  ({inv_data['period_label']})")
        print("=" * 62)
        print(body)
        print("=" * 62)
        if draft_only:
            log.info("--draft-only: draft ready. Edit it in the Invoice dialog "
                     "before the scheduled send date.")
        return

    # ── Validate send requirements ────────────────────────────────────────────
    gmail_user  = database.get_setting("gmail_address",    "").strip()
    gmail_pass  = database.get_setting("gmail_app_password", "").strip()
    client_email = settings["client_email"].strip()

    missing = [k for k, v in [("client_email", client_email),
                               ("gmail_address", gmail_user),
                               ("gmail_app_password", gmail_pass)] if not v]
    if missing:
        log.error("Missing settings: %s  — configure them in the app and retry.",
                  ", ".join(missing))
        sys.exit(1)

    # ── Generate PDF ──────────────────────────────────────────────────────────
    invoices_dir = APP_DIR / "invoices"
    invoices_dir.mkdir(exist_ok=True)
    pdf_path = str(invoices_dir / f"{inv_num}.pdf")

    log.info("Generating PDF → %s", pdf_path)
    invoice_pdf.generate_invoice(pdf_path, settings, inv_data)
    log.info("PDF generated successfully.")

    # ── Send ──────────────────────────────────────────────────────────────────
    subject = (f"Invoice {inv_num} — "
               f"AI Integration & Web Development Services — "
               f"{inv_data['period_label']}")

    log.info("Sending to %s via %s …", client_email, gmail_user)
    _smtp_send(gmail_user, gmail_pass, client_email, subject, body, pdf_path)
    log.info("✓  Invoice %s sent successfully to %s", inv_num, client_email)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Headless monthly invoice sender — PB&J Strategic Accounting")
    parser.add_argument(
        "--month", metavar="YYYY-MM",
        help="Target invoice month (default: current month)")
    parser.add_argument(
        "--draft-only", action="store_true",
        help="Generate and save an AI draft but do NOT send the invoice")
    parser.add_argument(
        "--show-draft", action="store_true",
        help="Print the current saved draft (or generate one) and exit")
    args = parser.parse_args()
    run(month_arg=args.month,
        draft_only=args.draft_only,
        show_draft=args.show_draft)
