import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from datetime import date, timedelta, datetime
import calendar
import csv
import os
import webbrowser
import urllib.parse

import database
import ai_parser
import pdf_report
import invoice_pdf
from constants import CATEGORIES, TRAINING_TYPES


def _smtp_send(gmail_user: str, app_password: str, to_email: str,
               subject: str, body: str, pdf_path: str | None,
               extra_attachments: list | None = None):
    """Send an email with optional PDF + extra file attachments via Gmail SMTP."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email.mime.image import MIMEImage
    from email import encoders

    from email.utils import formataddr, formatdate, make_msgid
    display_name = gmail_user.split("@")[0].replace(".", " ").title()
    msg = MIMEMultipart()
    msg["From"]       = formataddr((display_name, gmail_user))
    msg["To"]         = to_email
    msg["Subject"]    = subject
    msg["Date"]       = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=gmail_user.split("@")[1])
    msg["X-Mailer"]   = "Time Tracker — PB&J Strategic Accounting"
    msg.attach(MIMEText(body, "plain"))

    if pdf_path:
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f'attachment; filename="{os.path.basename(pdf_path)}"')
        msg.attach(part)

    for att_path in (extra_attachments or []):
        ext = os.path.splitext(att_path)[1].lower()
        img_exts = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg",
                    ".gif": "gif", ".webp": "webp", ".bmp": "bmp"}
        if ext in img_exts:
            with open(att_path, "rb") as f:
                part = MIMEImage(f.read(), _subtype=img_exts[ext])
        else:
            with open(att_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f'attachment; filename="{os.path.basename(att_path)}"')
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, app_password)
        server.sendmail(gmail_user, to_email, msg.as_string())

def _invoice_email_template(data: dict, settings: dict) -> str:
    """Standard invoice email body — same style every month, values filled in."""
    return (
        f"Dear {settings['company_name']},\n\n"
        f"Please find attached invoice {data['invoice_number']} covering all "
        f"{data['service_description']} for the month of {data['period_label']}.\n\n"
        f"Invoice Date:    {data['invoice_date']}\n"
        f"Service Period:  {data['period_label']} (all work this month)\n"
        f"Amount Due:      ${settings['retainer_amount']}\n\n"
        f"Hours worked as of {data['hours_as_of']} (informational):\n"
        f"  {data['hours_in_period']:.1f} hrs in {data['period_label']}"
        f"   |   {data['hours_total']:.1f} hrs total on record\n\n"
        f"Please don't hesitate to reach out with any questions.\n\n"
        f"Best regards,\n{settings['your_name']}"
    )


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ── Time utilities ────────────────────────────────────────────────────────────

def _parse_time_str(s: str):
    """Parse a flexible time string into a datetime (date part irrelevant). Returns None if unparseable."""
    if not s:
        return None
    s = s.strip().upper().replace(' ', '').replace('.', ':')
    for fmt in ("%I:%M%p", "%H:%M", "%I%p"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        h = int(s.rstrip('APM').split(':')[0])
        if s.endswith('PM') and h != 12:
            h += 12
        elif s.endswith('AM') and h == 12:
            h = 0
        if 0 <= h <= 23:
            return datetime(1900, 1, 1, h, 0)
    except (ValueError, IndexError):
        pass
    return None


def _normalize_time(s: str):
    """Normalize any time string to HH:MM (24h). Returns None if blank or unparseable."""
    s = s.strip()
    if not s:
        return None
    t = _parse_time_str(s)
    return t.strftime("%H:%M") if t else None


def _fmt_time_range(start, end) -> str:
    """Format HH:MM 24h times as a readable 12h range, e.g. '9:00 AM – 11:30 AM'."""
    def to12(t: str) -> str:
        try:
            h, m = map(int, t.split(':'))
            period = "AM" if h < 12 else "PM"
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {period}"
        except Exception:
            return t
    if start and end:
        return f"{to12(start)} – {to12(end)}"
    if start:
        return to12(start)
    if end:
        return to12(end)
    return ""


# ── Main Window ───────────────────────────────────────────────────────────────

class TimeTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Time Tracker — PB&J Strategic Accounting")
        self.geometry("1200x730")
        self.minsize(960, 600)

        database.init_db()

        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())
        self.entries = []

        self._build_toolbar()
        self._build_summary_bar()
        self._build_entries_panel()
        self._build_bottom_bar()
        self._load_entries()

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, height=58, corner_radius=0,
                           fg_color="#1c1917")
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar, text="⏱  Time Tracker",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=18)

        # Thin separator
        ctk.CTkFrame(bar, width=1, height=30, fg_color="#3a3230").pack(
            side="left", padx=4, pady=14)

        # Week navigation
        nav = ctk.CTkFrame(bar, fg_color="transparent")
        nav.pack(side="left", expand=True, fill="y")

        nav_btn = dict(width=30, height=28, fg_color="#c4006e",
                       hover_color="#8b004d", text_color="white", corner_radius=6)
        ctk.CTkButton(nav, text="◀", command=self._prev_week, **nav_btn).pack(
            side="left", padx=(8, 4), pady=15)
        self.week_label = ctk.CTkLabel(
            nav, text="", width=220,
            font=ctk.CTkFont(size=13, weight="bold"), text_color="white")
        self.week_label.pack(side="left")
        ctk.CTkButton(nav, text="▶", command=self._next_week, **nav_btn).pack(
            side="left", padx=(4, 8), pady=15)
        ctk.CTkButton(nav, text="Today", width=58, height=28,
                      fg_color="#c4006e", hover_color="#8b004d",
                      text_color="white", corner_radius=6,
                      command=self._goto_today).pack(side="left", pady=15)

        # Right buttons
        for label, cmd, color, hover, txt in [
            ("⚙  Settings", self._open_settings, "#5c5248", "#3a3230", "white"),
            ("CSV",          self._export_csv,    "#2ea3c5", "#1a7a98", "#1c1917"),
            ("PDF",          self._export_pdf,    "#c4006e", "#8b004d", "white"),
            ("Projects",     self._open_projects, "#ff43a4", "#e0007a", "#1c1917"),
            ("Invoice",      self._open_invoice,  "#b8882a", "#c49830", "#1c1917"),
        ]:
            ctk.CTkButton(
                bar, text=label, width=80, height=28,
                fg_color=color, hover_color=hover,
                text_color=txt, corner_radius=6,
                command=cmd,
            ).pack(side="right", padx=5, pady=15)

    # ── Summary bar ───────────────────────────────────────────────────────────

    def _build_summary_bar(self):
        bar = ctk.CTkFrame(self, height=56, corner_radius=0,
                           fg_color="#fff0f8")
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self.total_label = ctk.CTkLabel(
            bar, text="0.00 hrs this week",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#1c1917",
        )
        self.total_label.pack(side="left", padx=20)

        ctk.CTkFrame(bar, width=1, height=28, fg_color="#ddd6cf").pack(
            side="left", padx=4, pady=14)

        self.count_label = ctk.CTkLabel(
            bar, text="0 entries",
            font=ctk.CTkFont(size=11),
            text_color="#5c5248",
        )
        self.count_label.pack(side="left", padx=10)

        ctk.CTkFrame(bar, width=1, height=28, fg_color="#ddd6cf").pack(
            side="left", padx=4, pady=14)

        self.cat_label = ctk.CTkLabel(
            bar, text="",
            font=ctk.CTkFont(size=11),
            text_color="#3a3230",
            wraplength=700, justify="left",
        )
        self.cat_label.pack(side="left", padx=10, fill="x", expand=True)

        # Rate display on right
        self.rate_label = ctk.CTkLabel(
            bar, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#c4006e",
        )
        self.rate_label.pack(side="right", padx=20)

    # ── Entries panel ─────────────────────────────────────────────────────────

    def _build_entries_panel(self):
        panel = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        panel.pack(fill="both", expand=True, padx=10, pady=(6, 0))

        btn_row = ctk.CTkFrame(panel, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 5))

        ctk.CTkButton(btn_row, text="＋  Add Entry", width=112,
                      command=self._add_entry_dialog).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="✏  Edit", width=78,
                      fg_color="#3a3230", hover_color="#1c1917",
                      command=self._edit_entry).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="🗑  Delete", width=85,
                      fg_color="#b03030", hover_color="#8a2020",
                      command=self._delete_entry).pack(side="left")

        tree_frame = ctk.CTkFrame(panel)
        tree_frame.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TT.Treeview",
                        rowheight=32, font=("Segoe UI", 10),
                        background="white", fieldbackground="white",
                        foreground="#1c1917", borderwidth=0)
        style.configure("TT.Treeview.Heading",
                        font=("Segoe UI", 10, "bold"),
                        background="#1c1917", foreground="white",
                        relief="flat", padding=(6, 6))
        style.map("TT.Treeview",
                  background=[("selected", "#ffd6ec")],
                  foreground=[("selected", "white")])

        cols = ("date", "time", "hours", "category", "description")
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                 show="headings", selectmode="browse",
                                 style="TT.Treeview")

        self.tree.heading("date",        text="Date",        anchor="w")
        self.tree.heading("time",        text="Time",        anchor="w")
        self.tree.heading("hours",       text="Hrs",         anchor="center")
        self.tree.heading("category",    text="Category",    anchor="w")
        self.tree.heading("description", text="Description", anchor="w")

        self.tree.column("date",        width=92,  minwidth=80,  stretch=False)
        self.tree.column("time",        width=148, minwidth=110, stretch=False)
        self.tree.column("hours",       width=55,  minwidth=50,  anchor="center", stretch=False)
        self.tree.column("category",    width=148, minwidth=110, stretch=False)
        self.tree.column("description", minwidth=200)

        self.tree.tag_configure("even", background="white")
        self.tree.tag_configure("odd",  background="#f6f2ef")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", lambda _e: self._edit_entry())

    # ── Bottom bar ────────────────────────────────────────────────────────────

    def _build_bottom_bar(self):
        bar = ctk.CTkFrame(self, height=62, corner_radius=0,
                           fg_color="#f6f2ef")
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar, text="💬",
            font=ctk.CTkFont(size=16),
        ).pack(side="left", padx=(14, 2), pady=18)

        self.nl_entry = ctk.CTkEntry(
            bar,
            placeholder_text='Describe your work… e.g. "Tax prep 9am–11:30, met with client 2–3pm"',
            font=ctk.CTkFont(size=12),
            height=36,
        )
        self.nl_entry.pack(side="left", fill="x", expand=True, padx=6, pady=13)
        self.nl_entry.bind("<Return>", lambda _e: self._parse_nl_entry())

        self.ai_btn = ctk.CTkButton(
            bar, text="AI Log ✨", width=96, height=36,
            fg_color="#c4006e", hover_color="#8b004d",
            command=self._parse_nl_entry,
        )
        self.ai_btn.pack(side="left", padx=6, pady=13)

        self.status_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11),
            text_color="gray", width=200, anchor="e",
        )
        self.status_label.pack(side="right", padx=14)

    # ── Week navigation ────────────────────────────────────────────────────────

    def _update_week_label(self):
        week_end = self.week_start + timedelta(days=6)
        self.week_label.configure(
            text=f"{self.week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}"
        )

    def _prev_week(self):
        self.week_start -= timedelta(weeks=1)
        self._load_entries()

    def _next_week(self):
        self.week_start += timedelta(weeks=1)
        self._load_entries()

    def _goto_today(self):
        today = date.today()
        self.week_start = today - timedelta(days=today.weekday())
        self._load_entries()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_entries(self):
        self._update_week_label()
        week_end = self.week_start + timedelta(days=6)
        self.entries = database.get_entries_for_week(
            self.week_start.isoformat(), week_end.isoformat()
        )
        self._refresh_tree()
        self._refresh_summary()

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, e in enumerate(self.entries):
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert(
                "", "end", iid=str(e["id"]),
                values=(
                    e["date"],
                    _fmt_time_range(e.get("start_time"), e.get("end_time")),
                    f"{e['hours']:.2f}",
                    e.get("category", "Other"),
                    e["description"],
                ),
                tags=(tag,),
            )

    def _refresh_summary(self):
        total = sum(e["hours"] for e in self.entries)
        count = len(self.entries)
        self.total_label.configure(text=f"{total:.2f} hrs this week")
        self.count_label.configure(text=f"{count} entr{'y' if count == 1 else 'ies'}")

        cats: dict[str, float] = {}
        for e in self.entries:
            cat = e.get("category", "Other")
            cats[cat] = cats.get(cat, 0) + e["hours"]

        if cats:
            parts = [f"{c}: {h:.2f}h" for c, h in sorted(cats.items(), key=lambda x: -x[1])]
            self.cat_label.configure(text="  ·  ".join(parts), text_color="#3a3230")
        else:
            self.cat_label.configure(text="No entries yet — log your work below", text_color="#5c5248")

        rate_str = database.get_setting("hourly_rate", "").strip()
        if rate_str and total > 0:
            try:
                self.rate_label.configure(text=f"${total * float(rate_str):,.2f}")
            except ValueError:
                self.rate_label.configure(text="")
        else:
            self.rate_label.configure(text="")

    # ── Entry CRUD ────────────────────────────────────────────────────────────

    def _add_entry_dialog(self, prefill=None):
        EntryDialog(self, title="Add Time Entry",
                    on_save=self._load_entries, prefill=prefill)

    def _edit_entry(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select an entry to edit.")
            return
        entry = database.get_entry(int(sel[0]))
        if entry:
            EntryDialog(self, title="Edit Time Entry",
                        on_save=self._load_entries, entry=entry)

    def _delete_entry(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select an entry to delete.")
            return
        if messagebox.askyesno("Confirm Delete", "Delete this entry? This cannot be undone."):
            database.delete_entry(int(sel[0]))
            self._load_entries()

    # ── AI parsing ────────────────────────────────────────────────────────────

    def _parse_nl_entry(self):
        text = self.nl_entry.get().strip()
        if not text:
            return

        api_key = database.get_setting("api_key")
        if not api_key:
            messagebox.showwarning(
                "API Key Required",
                "Please set your Anthropic API key in Settings first."
            )
            self._open_settings()
            return

        self.ai_btn.configure(state="disabled", text="Parsing…")
        self.status_label.configure(text="AI is reading your entry…", text_color="#e67e22")

        def _work():
            try:
                results = ai_parser.parse_time_entries(text, api_key, date.today().isoformat())
                self.after(0, lambda: self._on_parse_ok(results))
            except Exception as exc:
                self.after(0, lambda: self._on_parse_err(str(exc)))

        threading.Thread(target=_work, daemon=True).start()

    def _on_parse_ok(self, results: list):
        self.ai_btn.configure(state="normal", text="AI Log ✨")
        self.nl_entry.delete(0, "end")
        count = len(results)
        if count == 1:
            self.status_label.configure(text="Parsed — review and save", text_color="#27ae60")
            self._add_entry_dialog(prefill=results[0])
        else:
            self.status_label.configure(
                text=f"Review {count} entries one at a time", text_color="#27ae60")
            for i, entry in enumerate(results):
                dlg = EntryDialog(self, title=f"Entry {i + 1} of {count}",
                                  on_save=self._load_entries, prefill=entry)
                self.wait_window(dlg)
            self._load_entries()

    def _on_parse_err(self, error: str):
        self.ai_btn.configure(state="normal", text="AI Log ✨")
        self.status_label.configure(text="Parse failed", text_color="#c0392b")
        messagebox.showerror("AI Parse Error", f"Could not parse the entry:\n\n{error}")

    # ── Exports ───────────────────────────────────────────────────────────────

    def _export_pdf(self):
        week_end = self.week_start + timedelta(days=6)
        dlg = DateRangeDialog(self, self.week_start, week_end, "PDF Export — Date Range")
        self.wait_window(dlg)
        if not dlg.result:
            return
        start_iso, end_iso = dlg.result
        entries = database.get_entries_for_week(start_iso, end_iso)
        path = filedialog.asksaveasfilename(
            title="Save PDF Report",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"time_report_{start_iso}_to_{end_iso}.pdf",
        )
        if not path:
            return
        settings = {
            "your_name":    database.get_setting("your_name",    "Consultant"),
            "company_name": database.get_setting("company_name", "Accounting Company"),
            "hourly_rate":  database.get_setting("hourly_rate",  ""),
        }
        try:
            pdf_report.generate_pdf(
                entries, start_iso, end_iso, path, settings,
                projects=database.get_projects(),
            )
            self.status_label.configure(text="PDF exported!", text_color="#27ae60")
            try:
                os.startfile(path)
            except Exception:
                pass
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _export_csv(self):
        week_end = self.week_start + timedelta(days=6)
        dlg = DateRangeDialog(self, self.week_start, week_end, "CSV Export — Date Range")
        self.wait_window(dlg)
        if not dlg.result:
            return
        start_iso, end_iso = dlg.result
        entries = database.get_entries_for_week(start_iso, end_iso)
        path = filedialog.asksaveasfilename(
            title="Save CSV Report",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"time_report_{start_iso}_to_{end_iso}.csv",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Start Time", "End Time", "Hours", "Category", "Description"])
                for e in entries:
                    writer.writerow([
                        e["date"],
                        e.get("start_time") or "",
                        e.get("end_time") or "",
                        e["hours"],
                        e.get("category", "Other"),
                        e["description"],
                    ])
                writer.writerow([])
                total = sum(e["hours"] for e in entries)
                writer.writerow(["TOTAL", "", "", f"{total:.2f}", "", ""])
            self.status_label.configure(text="CSV exported!", text_color="#27ae60")
            try:
                os.startfile(path)
            except Exception:
                pass
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _open_settings(self):
        SettingsDialog(self)

    def _open_projects(self):
        ProjectsDialog(self)

    def _open_invoice(self):
        InvoiceDialog(self)


# ── Entry Dialog ──────────────────────────────────────────────────────────────

class EntryDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, on_save, entry=None, prefill=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("550x460")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._on_save = on_save
        self._entry = entry
        data = prefill if prefill is not None else entry
        self._build_ui(data)

    def _build_ui(self, data):
        ctk.CTkLabel(self, text=self.title(),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#1c1917").pack(pady=(18, 12))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=28)
        form.columnconfigure(1, weight=1)

        lbl_kw = dict(anchor="w", font=ctk.CTkFont(size=12))
        pad = dict(pady=7, padx=(0, 14))

        # Date
        ctk.CTkLabel(form, text="Date:", **lbl_kw).grid(row=0, column=0, sticky="w", **pad)
        self.date_ent = ctk.CTkEntry(form, height=34, placeholder_text="YYYY-MM-DD")
        self.date_ent.grid(row=0, column=1, sticky="ew", pady=7)
        self.date_ent.insert(0, data.get("date", date.today().isoformat()) if data else date.today().isoformat())

        # Start / End time (side by side)
        ctk.CTkLabel(form, text="Time:", **lbl_kw).grid(row=1, column=0, sticky="w", **pad)
        time_row = ctk.CTkFrame(form, fg_color="transparent")
        time_row.grid(row=1, column=1, sticky="ew", pady=7)

        self.start_sv = ctk.StringVar()
        self.end_sv   = ctk.StringVar()

        ctk.CTkEntry(time_row, textvariable=self.start_sv,
                     width=108, height=34, placeholder_text="Start  9:00 AM").pack(side="left")
        ctk.CTkLabel(time_row, text="–", font=ctk.CTkFont(size=14),
                     text_color="#5c5248", width=18).pack(side="left")
        ctk.CTkEntry(time_row, textvariable=self.end_sv,
                     width=108, height=34, placeholder_text="End  5:00 PM").pack(side="left")
        ctk.CTkLabel(time_row, text="auto-fills hours",
                     font=ctk.CTkFont(size=10), text_color="#5c5248").pack(side="left", padx=(10, 0))

        if data:
            if data.get("start_time"):
                self.start_sv.set(_fmt_time_range(data["start_time"], None))
            if data.get("end_time"):
                self.end_sv.set(_fmt_time_range(None, data["end_time"]))

        self.start_sv.trace_add("write", self._calc_hours)
        self.end_sv.trace_add("write", self._calc_hours)

        # Hours
        ctk.CTkLabel(form, text="Hours:", **lbl_kw).grid(row=2, column=0, sticky="w", **pad)
        self.hours_sv = ctk.StringVar()
        self.hours_ent = ctk.CTkEntry(form, textvariable=self.hours_sv,
                                      height=34, placeholder_text="e.g. 2.5")
        self.hours_ent.grid(row=2, column=1, sticky="ew", pady=7)
        if data and "hours" in data:
            self.hours_sv.set(str(data["hours"]))

        # Category
        ctk.CTkLabel(form, text="Category:", **lbl_kw).grid(row=3, column=0, sticky="w", **pad)
        default_cat = data.get("category", "Bookkeeping") if data else "Bookkeeping"
        if default_cat not in CATEGORIES:
            default_cat = "Other"
        self.cat_var = ctk.StringVar(value=default_cat)
        ctk.CTkComboBox(form, values=CATEGORIES, variable=self.cat_var,
                        height=34,
                        command=self._on_category_change).grid(row=3, column=1, sticky="ew", pady=7)

        # Description
        ctk.CTkLabel(form, text="Description:", **lbl_kw).grid(row=4, column=0, sticky="nw", **pad)
        self.desc_box = ctk.CTkTextbox(form, height=80)
        self.desc_box.grid(row=4, column=1, sticky="ew", pady=7)
        if data and "description" in data:
            self.desc_box.insert("1.0", data["description"])

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=14)
        ctk.CTkButton(btn_row, text="Save Entry", width=120,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=8)

    def _on_category_change(self, value: str):
        if value == "Training Content":
            TrainingTypeDialog(self, on_select=self._apply_training_type)

    def _apply_training_type(self, training_type: str):
        if not training_type:
            return
        current = self.desc_box.get("1.0", "end").strip()
        if not current:
            self.desc_box.insert("1.0", f"{training_type}: ")
        elif not current.startswith(training_type):
            self.desc_box.delete("1.0", "end")
            self.desc_box.insert("1.0", f"{training_type}: {current}")
        self.desc_box.focus_set()
        self.desc_box.mark_set("insert", "end")

    def _calc_hours(self, *_):
        """Auto-fill hours from start and end time."""
        st = _parse_time_str(self.start_sv.get())
        et = _parse_time_str(self.end_sv.get())
        if st and et:
            delta = (et - st).total_seconds() / 3600
            if delta < 0:
                delta += 24  # overnight
            if 0 < delta <= 24:
                self.hours_sv.set(f"{delta:.2f}")

    def _save(self):
        date_val  = self.date_ent.get().strip()
        hours_raw = self.hours_sv.get().strip()
        cat_val   = self.cat_var.get().strip() or "Other"
        desc_val  = self.desc_box.get("1.0", "end").strip()
        start_val = _normalize_time(self.start_sv.get())
        end_val   = _normalize_time(self.end_sv.get())

        if not date_val or not desc_val:
            messagebox.showwarning("Required", "Date and description are required.", parent=self)
            return
        try:
            hours_val = float(hours_raw)
            if hours_val <= 0 or hours_val > 24:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Hours",
                                   "Hours must be a number between 0 and 24.", parent=self)
            return
        try:
            datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Invalid Date",
                                   "Date must be YYYY-MM-DD format.", parent=self)
            return

        if self._entry:
            database.update_entry(self._entry["id"], date_val, hours_val,
                                  desc_val, cat_val, start_val, end_val)
        else:
            database.add_entry(date_val, hours_val, desc_val, cat_val, start_val, end_val)

        self._on_save()
        self.destroy()


# ── Training Type Dialog ──────────────────────────────────────────────────────

class TrainingTypeDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.title("Training Content Type")
        self.geometry("400x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._on_select = on_select
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="What type of training content?",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#1c1917").pack(pady=(18, 12))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24)

        for i, t in enumerate(TRAINING_TYPES):
            row, col = divmod(i, 2)
            ctk.CTkButton(
                btn_frame, text=t, height=34, anchor="w",
                fg_color="#fff0f8", hover_color="#ffd6ec",
                text_color="#1c1917", corner_radius=6,
                command=lambda v=t: self._pick(v),
            ).grid(row=row, column=col, padx=4, pady=4, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Or type a custom description:",
                     font=ctk.CTkFont(size=11), text_color="#5c5248").pack(pady=(12, 4))

        self.custom_entry = ctk.CTkEntry(self, height=34, placeholder_text="e.g. Client onboarding walkthrough")
        self.custom_entry.pack(fill="x", padx=24)
        self.custom_entry.bind("<Return>", lambda _: self._pick_custom())

        row_btns = ctk.CTkFrame(self, fg_color="transparent")
        row_btns.pack(pady=12)
        ctk.CTkButton(row_btns, text="Confirm", width=110,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._pick_custom).pack(side="left", padx=6)
        ctk.CTkButton(row_btns, text="Skip", width=80,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=6)

    def _pick(self, value: str):
        self._on_select(value)
        self.destroy()

    def _pick_custom(self):
        val = self.custom_entry.get().strip()
        if val:
            self._on_select(val)
        self.destroy()


# ── Settings Dialog ────────────────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("560x660")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Settings",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#1c1917").pack(pady=(18, 6))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=30)
        form.columnconfigure(1, weight=1)

        fields = [
            ("Your Name:",          "your_name",          "e.g. Alexander Anderson",        False),
            ("Company Name:",       "company_name",        "Client company name",             False),
            ("Client Email:",       "client_email",        "client@example.com",              False),
            ("Retainer Amount ($):", "retainer_amount",    "e.g. 750.00",                    False),
            ("Hourly Rate ($):",    "hourly_rate",         "Optional — e.g. 85.00",           False),
            ("Anthropic API Key:",  "api_key",             "sk-ant-…",                        True),
            ("Gmail Address:",      "gmail_address",       "you@gmail.com",                   False),
            ("Gmail App Password:", "gmail_app_password",  "xxxx xxxx xxxx xxxx",             True),
            ("Venmo Username:",     "venmo_username",      "@YourVenmo",                      False),
        ]

        self._fields: dict[str, ctk.CTkEntry] = {}
        for i, (label, key, placeholder, secret) in enumerate(fields):
            ctk.CTkLabel(form, text=label, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(
                row=i, column=0, sticky="w", pady=7, padx=(0, 16))
            ent = ctk.CTkEntry(form, height=34, placeholder_text=placeholder,
                               show="*" if secret else "")
            ent.grid(row=i, column=1, sticky="ew", pady=7)
            val = database.get_setting(key)
            if val:
                ent.insert(0, val)
            self._fields[key] = ent

        ctk.CTkLabel(form,
                     text="Gmail App Password: Google Account → Security → 2-Step Verification → App Passwords",
                     font=ctk.CTkFont(size=9), text_color="#5c5248",
                     wraplength=380, justify="left").grid(
            row=len(fields), column=0, columnspan=2,
            sticky="w", pady=(2, 0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=16)
        ctk.CTkButton(btn_row, text="Save", width=120,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=8)

    def _save(self):
        for key, ent in self._fields.items():
            database.set_setting(key, ent.get().strip())
        messagebox.showinfo("Saved", "Settings saved successfully!", parent=self)
        self.destroy()


# ── Multi-Entry Preview Dialog ────────────────────────────────────────────────

class MultiEntryPreviewDialog(ctk.CTkToplevel):
    def __init__(self, parent, entries: list, on_added=None):
        super().__init__(parent)
        self._entries = entries
        self._on_added = on_added
        self.title(f"Add {len(entries)} Entries")
        self.geometry("720x420")
        self.minsize(600, 320)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._build_ui()

    def _build_ui(self):
        self.configure(fg_color="#f6f2ef")

        top = ctk.CTkFrame(self, fg_color="#1c1917", corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text=f"AI found {len(self._entries)} entries — review before adding",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").pack(side="left", padx=18, pady=11)

        tree_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=8)
        tree_frame.pack(fill="both", expand=True, padx=14, pady=(10, 4))

        style = ttk.Style()
        style.configure("Multi.Treeview",
                        font=("Segoe UI", 10), rowheight=28,
                        background="white", fieldbackground="white",
                        foreground="#1c1917")
        style.configure("Multi.Treeview.Heading",
                        font=("Segoe UI", 10, "bold"),
                        background="#fff0f8", foreground="#1c1917", relief="flat")
        style.map("Multi.Treeview", background=[("selected", "#ffd6ec")])

        cols = ("date", "hours", "category", "description")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   style="Multi.Treeview", selectmode="none")
        for col, label, width in [
            ("date",        "Date",        90),
            ("hours",       "Hrs",         50),
            ("category",    "Category",    150),
            ("description", "Description", 380),
        ]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor="w" if col == "description" else "center",
                              stretch=(col == "description"))

        for e in self._entries:
            time_str = ""
            if e.get("start_time") and e.get("end_time"):
                time_str = f" ({e['start_time']}–{e['end_time']})"
            self._tree.insert("", "end", values=(
                e["date"],
                f"{e['hours']:.1f}",
                e.get("category", "Other"),
                e["description"] + time_str,
            ))

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        vsb.pack(side="right", fill="y", pady=6, padx=(0, 4))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        total = sum(e["hours"] for e in self._entries)
        ctk.CTkButton(btn_row,
                      text=f"Add All {len(self._entries)} Entries  ({total:.1f} hrs total)",
                      width=260, height=34,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._add_all).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100, height=34,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=8)

    def _add_all(self):
        for e in self._entries:
            database.add_entry(
                e["date"], e["hours"], e["description"],
                e.get("category", "Other"),
                e.get("start_time"), e.get("end_time"),
            )
        if self._on_added:
            self._on_added()
        self.destroy()


# ── Date Range Dialog ─────────────────────────────────────────────────────────

class CalendarPopup(ctk.CTkToplevel):
    """Borderless calendar dropdown that calls on_select(iso_str) on day click."""

    def __init__(self, parent, anchor_widget, initial_date: date, on_select):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(fg_color="#ddd6cf")   # 2-px border effect
        self._on_select = on_select
        self._build(initial_date)
        self._position(anchor_widget)
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _: self.destroy())

    def _build(self, d: date):
        from tkcalendar import Calendar
        self._cal = Calendar(
            self, selectmode="day",
            year=d.year, month=d.month, day=d.day,
            date_pattern="yyyy-mm-dd",
            background="#1c1917",
            foreground="white",
            selectbackground="#c4006e",
            selectforeground="white",
            normalbackground="white",
            normalforeground="#1c1917",
            weekendbackground="#fff0f8",
            weekendforeground="#c4006e",
            othermonthbackground="#f6f2ef",
            othermonthforeground="#9e8e82",
            headersbackground="#fff0f8",
            headersforeground="#5c5248",
            bordercolor="#ddd6cf",
            font=("Segoe UI", 9),
        )
        self._cal.pack(padx=2, pady=2)
        self._cal.bind("<<CalendarSelected>>", self._picked)

    def _position(self, widget):
        self.update_idletasks()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        self.geometry(f"+{x}+{y}")

    def _picked(self, _=None):
        self._on_select(self._cal.get_date())
        self.destroy()


class DateRangeDialog(ctk.CTkToplevel):
    """Returns (start_iso, end_iso) via .result after the user clicks Export."""

    def __init__(self, parent, default_start: date, default_end: date, title="Export Date Range"):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self.result = None
        self._build_ui(default_start, default_end)

    def _build_ui(self, ds: date, de: date):
        self.configure(fg_color="#f6f2ef")
        ctk.CTkLabel(self, text="Select date range for the report",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#1c1917").pack(pady=(18, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=30, fill="x")
        form.columnconfigure(1, weight=1)

        self._start_var = tk.StringVar(value=ds.isoformat())
        self._end_var   = tk.StringVar(value=de.isoformat())

        for i, (label, var) in enumerate([("From:", self._start_var), ("To:", self._end_var)]):
            ctk.CTkLabel(form, text=label, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(
                row=i, column=0, sticky="w", pady=8, padx=(0, 12))

            row_f = ctk.CTkFrame(form, fg_color="transparent")
            row_f.grid(row=i, column=1, sticky="ew", pady=8)
            row_f.columnconfigure(0, weight=1)

            ent = ctk.CTkEntry(row_f, height=34, textvariable=var)
            ent.grid(row=0, column=0, sticky="ew", padx=(0, 6))

            ctk.CTkButton(
                row_f, text="📅", width=38, height=34,
                fg_color="#c4006e", hover_color="#8b004d",
                text_color="white", corner_radius=6,
                command=lambda v=var, w=ent: self._open_cal(v, w),
            ).grid(row=0, column=1)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=14)
        ctk.CTkButton(btn_row, text="Export", width=120,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._confirm).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=8)

    def _open_cal(self, var: tk.StringVar, anchor):
        try:
            d = date.fromisoformat(var.get())
        except ValueError:
            d = date.today()
        CalendarPopup(self, anchor, d, lambda iso: var.set(iso))

    def _confirm(self):
        s, e = self._start_var.get().strip(), self._end_var.get().strip()
        try:
            sd = date.fromisoformat(s)
            ed = date.fromisoformat(e)
        except ValueError:
            messagebox.showwarning("Invalid Date",
                                   "Please select valid dates.", parent=self)
            return
        if ed < sd:
            messagebox.showwarning("Invalid Range",
                                   "End date must be on or after start date.", parent=self)
            return
        self.result = (s, e)
        self.destroy()


# ── Projects Dialog ───────────────────────────────────────────────────────────

class ProjectsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Projects & Priorities")
        self.geometry("780x520")
        self.minsize(680, 400)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._build_ui()
        self._load()

    def _build_ui(self):
        self.configure(fg_color="#f6f2ef")

        top = ctk.CTkFrame(self, fg_color="#1c1917", corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Projects & Priorities",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white").pack(side="left", padx=20, pady=12)

        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkButton(btn_bar, text="+ Add Project", width=130,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._add).pack(side="left", padx=(0, 8))
        self._edit_btn = ctk.CTkButton(btn_bar, text="Edit", width=90,
                                       fg_color="#2ea3c5", hover_color="#1a7a98",
                                       text_color="#1c1917",
                                       state="disabled", command=self._edit)
        self._edit_btn.pack(side="left", padx=(0, 8))
        self._del_btn = ctk.CTkButton(btn_bar, text="Delete", width=90,
                                      fg_color="#8b2635", hover_color="#6b1c28",
                                      state="disabled", command=self._delete)
        self._del_btn.pack(side="left")

        tree_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=8)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        style = ttk.Style()
        style.configure("Proj.Treeview",
                        font=("Segoe UI", 10), rowheight=30,
                        background="white", fieldbackground="white",
                        foreground="#1c1917")
        style.configure("Proj.Treeview.Heading",
                        font=("Segoe UI", 10, "bold"),
                        background="#fff0f8", foreground="#1c1917",
                        relief="flat")
        style.map("Proj.Treeview", background=[("selected", "#ffd6ec")])

        cols = ("priority", "name", "status", "completion", "due_date")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   style="Proj.Treeview", selectmode="browse")
        for col, label, width, anchor in [
            ("priority",   "Priority",   80,  "center"),
            ("name",       "Project",    260, "w"),
            ("status",     "Status",     100, "center"),
            ("completion", "% Done",     70,  "center"),
            ("due_date",   "Due Date",   100, "center"),
        ]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))

        self._tree.tag_configure("high",     foreground="#8b2635")
        self._tree.tag_configure("medium",   foreground="#c4006e")
        self._tree.tag_configure("low",      foreground="#3a3230")
        self._tree.tag_configure("done",     foreground="#5c5248")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        vsb.pack(side="right", fill="y", pady=6, padx=(0, 4))

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _: self._edit())

    def _load(self):
        self._tree.delete(*self._tree.get_children())
        self._projects = {p["id"]: p for p in database.get_projects()}
        for p in self._projects.values():
            tag = p["status"].lower().replace(" ", "_") if p["status"] != "Active" else "medium"
            if p["priority"] == "High":
                tag = "high"
            elif p["status"] == "Completed":
                tag = "done"
            due = p.get("due_date") or ""
            pct = "Ongoing" if p.get("is_ongoing") else f"{p['completion']}%"
            self._tree.insert("", "end", iid=str(p["id"]),
                              values=(p["priority"], p["name"], p["status"], pct, due),
                              tags=(tag,))
        self._on_select()

    def _on_select(self, *_):
        sel = bool(self._tree.selection())
        state = "normal" if sel else "disabled"
        self._edit_btn.configure(state=state)
        self._del_btn.configure(state=state)

    def _selected_id(self):
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        ProjectEditDialog(self, on_save=self._load)

    def _edit(self):
        pid = self._selected_id()
        if pid is None:
            return
        ProjectEditDialog(self, project=self._projects[pid], on_save=self._load)

    def _delete(self):
        pid = self._selected_id()
        if pid is None:
            return
        name = self._projects[pid]["name"]
        if messagebox.askyesno("Delete Project",
                               f'Delete project "{name}"?\nThis cannot be undone.',
                               parent=self):
            database.delete_project(pid)
            self._load()


class ProjectEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, project=None, on_save=None):
        super().__init__(parent)
        self._project = project
        self._on_save = on_save
        self.title("Edit Project" if project else "Add Project")
        self.geometry("520x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._build_ui()

    def _build_ui(self):
        self.configure(fg_color="#f6f2ef")
        p = self._project or {}

        ctk.CTkLabel(self, text="Edit Project" if p else "Add Project",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#1c1917").pack(pady=(18, 4))

        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24)
        form.columnconfigure(1, weight=1)

        row = 0

        def lbl(text):
            nonlocal row
            ctk.CTkLabel(form, text=text, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(
                row=row, column=0, sticky="w", pady=(10, 2), padx=(0, 12))

        # Name
        lbl("Project Name:")
        self._name = ctk.CTkEntry(form, height=34, placeholder_text="e.g. Client Website Redesign")
        self._name.grid(row=row, column=1, sticky="ew", pady=(10, 2))
        if p.get("name"):
            self._name.insert(0, p["name"])
        row += 1

        # Description
        lbl("Description:")
        self._desc = ctk.CTkTextbox(form, height=70, corner_radius=6)
        self._desc.grid(row=row, column=1, sticky="ew", pady=(10, 2))
        if p.get("description"):
            self._desc.insert("1.0", p["description"])
        row += 1

        # Priority
        lbl("Priority:")
        self._priority = ctk.CTkSegmentedButton(
            form, values=["High", "Medium", "Low"],
            fg_color="#fff0f8", selected_color="#c4006e",
            selected_hover_color="#8b004d", unselected_color="#ede8e3",
            text_color="#1c1917", height=32)
        self._priority.grid(row=row, column=1, sticky="w", pady=(10, 2))
        self._priority.set(p.get("priority", "Medium"))
        row += 1

        # Status
        lbl("Status:")
        self._status = ctk.CTkComboBox(
            form, values=["Active", "On Hold", "Completed"],
            height=34, state="readonly")
        self._status.grid(row=row, column=1, sticky="w", pady=(10, 2))
        self._status.set(p.get("status", "Active"))
        row += 1

        # Ongoing toggle
        lbl("Ongoing:")
        self._ongoing_var = tk.BooleanVar(value=bool(p.get("is_ongoing", 0)))
        ongoing_cb = ctk.CTkCheckBox(form, text="No fixed completion % (ongoing work)",
                                     variable=self._ongoing_var,
                                     fg_color="#c4006e", hover_color="#8b004d",
                                     command=self._toggle_ongoing)
        ongoing_cb.grid(row=row, column=1, sticky="w", pady=(10, 2))
        row += 1

        # Completion slider
        lbl("Completion:")
        self._completion_row = row
        slider_frame = ctk.CTkFrame(form, fg_color="transparent")
        slider_frame.grid(row=row, column=1, sticky="ew", pady=(10, 2))
        self._completion_label = ctk.CTkLabel(slider_frame, text=f"{p.get('completion', 0)}%",
                                               width=40, font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#c4006e")
        self._completion_label.pack(side="left", padx=(0, 8))
        self._completion = ctk.CTkSlider(slider_frame, from_=0, to=100, number_of_steps=20,
                                          command=self._on_slider)
        self._completion.set(p.get("completion", 0))
        self._completion.pack(side="left", fill="x", expand=True)
        self._slider_frame = slider_frame
        row += 1
        self._toggle_ongoing()

        # Due date
        lbl("Due Date:")
        self._due = ctk.CTkEntry(form, height=34, placeholder_text="YYYY-MM-DD (optional)")
        self._due.grid(row=row, column=1, sticky="w", pady=(10, 2))
        if p.get("due_date"):
            self._due.insert(0, p["due_date"])
        row += 1

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=14)
        ctk.CTkButton(btn_row, text="Save", width=120,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", width=100,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=8)

    def _on_slider(self, value):
        self._completion_label.configure(text=f"{int(value)}%")

    def _toggle_ongoing(self):
        if self._ongoing_var.get():
            self._slider_frame.grid_remove()
        else:
            self._slider_frame.grid()

    def _save(self):
        name = self._name.get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Project name is required.", parent=self)
            return
        desc = self._desc.get("1.0", "end-1c").strip()
        priority = self._priority.get()
        status = self._status.get()
        is_ongoing = int(self._ongoing_var.get())
        completion = 0 if is_ongoing else int(self._completion.get())
        due = self._due.get().strip() or None
        if due:
            try:
                datetime.strptime(due, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("Invalid Date",
                                       "Due date must be YYYY-MM-DD format.", parent=self)
                return
        if self._project:
            database.update_project(self._project["id"], name, desc, priority,
                                    status, completion, due, is_ongoing)
        else:
            database.add_project(name, desc, priority, status, completion, due, is_ongoing)
        if self._on_save:
            self._on_save()
        self.destroy()


# ── Invoice Dialog ────────────────────────────────────────────────────────────

class InvoiceDialog(ctk.CTkToplevel):
    _DEFAULT_SERVICE = "AI Integration & Web Development Services — Monthly Retainer"

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Generate Invoice")
        self.geometry("580x660")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._pdf_path = None
        self._row = 0
        self._email_body_inv = None   # track which draft is loaded
        self._build_ui()
        self._update_computed()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.configure(fg_color="#f6f2ef")

        top = ctk.CTkFrame(self, fg_color="#1c1917", corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Generate Invoice",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white").pack(side="left", padx=20, pady=12)
        ctk.CTkLabel(top, text="flat-rate retainer",
                     font=ctk.CTkFont(size=11), text_color="#9e8e82").pack(
            side="left", padx=4)

        # Auto-send toggle — right side of header
        auto_frame = ctk.CTkFrame(top, fg_color="transparent")
        auto_frame.pack(side="right", padx=20, pady=6)
        toggle_row = ctk.CTkFrame(auto_frame, fg_color="transparent")
        toggle_row.pack()
        ctk.CTkLabel(toggle_row, text="Auto-send on 1st",
                     font=ctk.CTkFont(size=11), text_color="#9e8e82").pack(
            side="left", padx=(0, 8))
        self._auto_var = tk.BooleanVar(
            value=database.get_setting("auto_invoice_enabled", "1") == "1")
        ctk.CTkSwitch(toggle_row, text="", variable=self._auto_var,
                      width=46, button_color="#c4006e", button_hover_color="#8b004d",
                      progress_color="#c4006e",
                      command=self._toggle_auto_send).pack(side="left")
        self._next_run_lbl = ctk.CTkLabel(
            auto_frame, text=self._next_run_text(),
            font=ctk.CTkFont(size=9), text_color="#b8882a")
        self._next_run_lbl.pack(pady=(2, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(12, 4))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        def section(text):
            ctk.CTkLabel(body, text=text,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#5c5248").grid(
                row=self._row, column=0, columnspan=2,
                sticky="w", pady=(10, 2))
            self._row += 1

        def lbl(text, col):
            ctk.CTkLabel(body, text=text, anchor="w",
                         font=ctk.CTkFont(size=11)).grid(
                row=self._row, column=col, sticky="w",
                pady=(4, 1), padx=(8 if col else 0, 0))

        def advance():
            self._row += 1

        # ── INVOICE DETAILS ──────────────────────────────────────────────
        section("INVOICE DETAILS")

        # Invoice Date  |  Bill To
        lbl("Invoice Date", 0); lbl("Bill To", 1); advance()

        today = date.today()
        self._inv_date_var = tk.StringVar(value=date(today.year, today.month, 1).isoformat())
        self._inv_date_var.trace_add("write", lambda *_: self._update_computed())

        inv_f = ctk.CTkFrame(body, fg_color="transparent")
        inv_f.grid(row=self._row, column=0, sticky="ew", pady=(0, 6))
        inv_f.columnconfigure(0, weight=1)
        inv_ent = ctk.CTkEntry(inv_f, height=32, textvariable=self._inv_date_var)
        inv_ent.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(inv_f, text="📅", width=36, height=32,
                      fg_color="#c4006e", hover_color="#8b004d", text_color="white",
                      corner_radius=6,
                      command=lambda: self._open_cal(self._inv_date_var, inv_ent)
                      ).grid(row=0, column=1)

        self._bill_to = ctk.CTkEntry(body, height=32)
        self._bill_to.insert(0, database.get_setting("company_name", "PB&J Strategic Accounting"))
        self._bill_to.grid(row=self._row, column=1, sticky="ew",
                           pady=(0, 6), padx=(8, 0))
        advance()

        # Invoice #  |  Client Email
        lbl("Invoice #", 0); lbl("Client Email", 1); advance()
        self._inv_num_lbl = ctk.CTkLabel(body, text="",  anchor="w",
                                         font=ctk.CTkFont(size=13, weight="bold"),
                                         text_color="#c4006e")
        self._inv_num_lbl.grid(row=self._row, column=0, sticky="w", pady=(0, 6))
        self._client_email = ctk.CTkEntry(body, height=32)
        self._client_email.insert(0, database.get_setting("client_email", ""))
        self._client_email.grid(row=self._row, column=1, sticky="ew",
                                pady=(0, 6), padx=(8, 0))
        advance()

        # Period  |  Amount
        lbl("Period Covered", 0); lbl("Retainer Amount ($)", 1); advance()
        self._period_lbl = ctk.CTkLabel(body, text="", anchor="w",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#1c1917")
        self._period_lbl.grid(row=self._row, column=0, sticky="w", pady=(0, 6))
        self._amount = ctk.CTkEntry(body, height=32)
        self._amount.insert(0, database.get_setting("retainer_amount", "750.00"))
        self._amount.grid(row=self._row, column=1, sticky="ew",
                          pady=(0, 6), padx=(8, 0))
        advance()

        # Service description — full width
        section("SERVICE DESCRIPTION")
        self._service = ctk.CTkTextbox(body, height=52, corner_radius=6)
        self._service.insert("1.0", database.get_setting("invoice_service",
                                                          self._DEFAULT_SERVICE))
        self._service.grid(row=self._row, column=0, columnspan=2,
                           sticky="ew", pady=(0, 6))
        advance()

        # ── HOURS (INFORMATIONAL) ────────────────────────────────────────
        section("HOURS — INFORMATIONAL ONLY")
        lbl("Hours as of", 0); advance()

        self._hrs_date_var = tk.StringVar(value=today.isoformat())
        self._hrs_date_var.trace_add("write", lambda *_: self._update_computed())

        hrs_f = ctk.CTkFrame(body, fg_color="transparent")
        hrs_f.grid(row=self._row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        hrs_ent = ctk.CTkEntry(hrs_f, height=32, textvariable=self._hrs_date_var, width=180)
        hrs_ent.grid(row=0, column=0, padx=(0, 5))
        ctk.CTkButton(hrs_f, text="📅", width=36, height=32,
                      fg_color="#c4006e", hover_color="#8b004d", text_color="white",
                      corner_radius=6,
                      command=lambda: self._open_cal(self._hrs_date_var, hrs_ent)
                      ).grid(row=0, column=1)
        advance()

        self._hours_lbl = ctk.CTkLabel(body, text="", anchor="w",
                                       font=ctk.CTkFont(size=11),
                                       text_color="#5c5248")
        self._hours_lbl.grid(row=self._row, column=0, columnspan=2,
                             sticky="w", pady=(0, 8))
        advance()

        # ── EMAIL BODY ────────────────────────────────────────────────────
        section("EMAIL BODY")
        ai_row = ctk.CTkFrame(body, fg_color="transparent")
        ai_row.grid(row=self._row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._ai_btn = ctk.CTkButton(
            ai_row, text="📋 Fill Template", width=130, height=28,
            fg_color="#2ea3c5", hover_color="#1d7a94", text_color="white",
            command=self._generate_ai_body)
        self._ai_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            ai_row, text="💾 Save Draft", width=110, height=28,
            fg_color="#5c5248", hover_color="#3a3230", text_color="white",
            command=self._save_draft).pack(side="left", padx=(0, 10))
        self._draft_saved_lbl = ctk.CTkLabel(
            ai_row, text="", font=ctk.CTkFont(size=10), text_color="#2ea3c5")
        self._draft_saved_lbl.pack(side="left")
        advance()
        self._email_body = ctk.CTkTextbox(body, height=130, corner_radius=6)
        self._email_body.grid(row=self._row, column=0, columnspan=2,
                              sticky="ew", pady=(0, 6))
        advance()

        # ── Buttons ──────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="Generate PDF", width=120,
                      fg_color="#1c1917", hover_color="#3a3230",
                      command=self._generate_pdf).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="👁 Preview", width=100,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self._preview_email).pack(side="left", padx=4)
        self._send_btn = ctk.CTkButton(btn_row, text="Send Invoice", width=120,
                                       fg_color="#c4006e", hover_color="#8b004d",
                                       command=self._send_gmail)
        self._send_btn.pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Send Receipt", width=120,
                      fg_color="#b8882a", hover_color="#c49830", text_color="#1c1917",
                      command=self._send_receipt).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Close", width=80,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=4)

    # ── Live updates ─────────────────────────────────────────────────────────

    def _update_computed(self):
        try:
            inv_d = date.fromisoformat(self._inv_date_var.get())
        except ValueError:
            return
        self._inv_num_lbl.configure(text=f"INV-{inv_d.year}{inv_d.month:02d}")
        self._period_lbl.configure(text=inv_d.strftime("%B %Y"))

        try:
            hrs_d = date.fromisoformat(self._hrs_date_var.get())
        except ValueError:
            hrs_d = date.today()

        p_start  = inv_d.replace(day=1).isoformat()
        last_day = calendar.monthrange(inv_d.year, inv_d.month)[1]
        p_end    = inv_d.replace(day=last_day).isoformat()
        hrs_p    = database.get_hours_in_period(p_start, p_end)
        hrs_t    = database.get_total_hours_up_to(hrs_d.isoformat())
        self._hours_lbl.configure(
            text=f"{hrs_p:.1f} hrs in {inv_d.strftime('%B %Y')}   |   "
                 f"{hrs_t:.1f} hrs total as of {hrs_d.strftime('%b %d, %Y')}")

        # Load saved draft for this invoice number (only when it changes)
        inv_num = f"INV-{inv_d.year}{inv_d.month:02d}"
        if inv_num != self._email_body_inv:
            self._email_body_inv = inv_num
            saved = database.get_setting(f"email_draft_{inv_num}", "")
            self._email_body.delete("1.0", "end")
            if saved:
                self._email_body.insert("1.0", saved)

    def _open_cal(self, var: tk.StringVar, anchor):
        try:
            d = date.fromisoformat(var.get())
        except ValueError:
            d = date.today()
        CalendarPopup(self, anchor, d, lambda iso: var.set(iso))

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _save_settings(self):
        database.set_setting("company_name",    self._bill_to.get().strip())
        database.set_setting("client_email",    self._client_email.get().strip())
        database.set_setting("retainer_amount", self._amount.get().strip())
        database.set_setting("invoice_service", self._service.get("1.0", "end-1c").strip())

    def _build_data(self):
        try:
            inv_d = date.fromisoformat(self._inv_date_var.get())
        except ValueError:
            messagebox.showwarning("Invalid Date", "Enter a valid invoice date.", parent=self)
            return None
        try:
            hrs_d = date.fromisoformat(self._hrs_date_var.get())
        except ValueError:
            hrs_d = date.today()

        p_start  = inv_d.replace(day=1).isoformat()
        last_day = calendar.monthrange(inv_d.year, inv_d.month)[1]
        p_end    = inv_d.replace(day=last_day).isoformat()
        return {
            "invoice_number":      f"INV-{inv_d.year}{inv_d.month:02d}",
            "invoice_date":        inv_d.strftime("%B %d, %Y"),
            "period_label":        inv_d.strftime("%B %Y"),
            "period_start":        p_start,
            "period_end":          p_end,
            "service_description": self._service.get("1.0", "end-1c").strip(),
            "hours_as_of":         hrs_d.strftime("%B %d, %Y"),
            "hours_in_period":     database.get_hours_in_period(p_start, p_end),
            "hours_total":         database.get_total_hours_up_to(hrs_d.isoformat()),
        }

    def _get_settings(self):
        return {
            "your_name":       database.get_setting("your_name", "Consultant"),
            "company_name":    self._bill_to.get().strip(),
            "client_email":    self._client_email.get().strip(),
            "retainer_amount": self._amount.get().strip(),
            "venmo_username":  database.get_setting("venmo_username", ""),
        }

    # ── Actions ──────────────────────────────────────────────────────────────

    def _ensure_pdf(self):
        """Generate PDF to the invoices folder if not already done. Returns True on success."""
        if self._pdf_path and os.path.exists(self._pdf_path):
            return True
        data = self._build_data()
        if not data:
            return False
        self._save_settings()
        invoices_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "invoices")
        os.makedirs(invoices_dir, exist_ok=True)
        path = os.path.join(invoices_dir, f"{data['invoice_number']}.pdf")
        try:
            invoice_pdf.generate_invoice(path, self._get_settings(), data)
            self._pdf_path = path
            return True
        except Exception as exc:
            messagebox.showerror("PDF Error", str(exc), parent=self)
            return False

    def _generate_pdf(self):
        data = self._build_data()
        if not data:
            return
        self._save_settings()
        path = filedialog.asksaveasfilename(
            title="Save Invoice",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{data['invoice_number']}.pdf",
        )
        if not path:
            return
        try:
            invoice_pdf.generate_invoice(path, self._get_settings(), data)
            self._pdf_path = path
            messagebox.showinfo("Saved", f"Invoice saved:\n{path}", parent=self)
            try:
                os.startfile(path)
            except Exception:
                pass
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _build_subject(self, data):
        return (f"Invoice {data['invoice_number']} — "
                f"AI Integration & Web Development Services — {data['period_label']}")

    def _build_body(self, data, settings):
        """Return the editable body textbox content, falling back to standard template."""
        text = self._email_body.get("1.0", "end-1c").strip()
        return text if text else _invoice_email_template(data, settings)

    def _send_gmail(self):
        gmail_user = database.get_setting("gmail_address", "").strip()
        gmail_pass = database.get_setting("gmail_app_password", "").strip()
        client_email = self._client_email.get().strip()

        if not client_email:
            messagebox.showwarning("Missing Email",
                                   "Enter the client email address.", parent=self)
            return

        if not gmail_user or not gmail_pass:
            messagebox.showinfo(
                "Gmail Not Configured",
                "Add your Gmail address and App Password in Settings to send directly.\n\n"
                "Go to: Google Account → Security → 2-Step Verification → App Passwords",
                parent=self)
            return

        if not self._ensure_pdf():
            return

        data = self._build_data()
        if not data:
            return
        s = self._get_settings()

        # Persist whatever is in the body box as the draft for this invoice
        body_text = self._build_body(data, s)
        database.set_setting(f"email_draft_{data['invoice_number']}", body_text)

        self._send_btn.configure(state="disabled", text="Sending…")

        def do_send():
            try:
                _smtp_send(gmail_user, gmail_pass, client_email,
                           self._build_subject(data),
                           body_text,
                           self._pdf_path)
                self.after(0, lambda: messagebox.showinfo(
                    "Sent!", f"Invoice sent to {client_email}.", parent=self))
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror(
                    "Send Failed",
                    f"{e}\n\nDouble-check your Gmail address and App Password in Settings.",
                    parent=self))
            finally:
                self.after(0, lambda: self._send_btn.configure(
                    state="normal", text="Send Invoice"))

        threading.Thread(target=do_send, daemon=True).start()

    def _next_run_text(self) -> str:
        if not self._auto_var.get():
            return "auto-send off"
        now = datetime.now()
        if now.day == 1 and now.hour < 11:
            next_run = now.replace(hour=11, minute=0, second=0, microsecond=0)
        elif now.month == 12:
            next_run = datetime(now.year + 1, 1, 1, 11, 0)
        else:
            next_run = datetime(now.year, now.month + 1, 1, 11, 0)
        return f"Next send: {next_run.strftime('%b')} {next_run.day} at 11:00 AM"

    def _toggle_auto_send(self):
        enabled = self._auto_var.get()
        database.set_setting("auto_invoice_enabled", "1" if enabled else "0")
        self._next_run_lbl.configure(text=self._next_run_text())

    def _save_draft(self):
        """Persist the current email body to the database without sending."""
        data = self._build_data()
        if not data:
            return
        body_text = self._email_body.get("1.0", "end-1c").strip()
        database.set_setting(f"email_draft_{data['invoice_number']}", body_text)
        self._draft_saved_lbl.configure(text="✓ saved")
        self.after(2500, lambda: self._draft_saved_lbl.configure(text=""))

    def _preview_email(self):
        """Open a read-only preview showing exactly what the auto-sender will send."""
        data = self._build_data()
        if not data:
            return
        s = self._get_settings()
        subject  = self._build_subject(data)
        body     = self._build_body(data, s)
        to_email = s.get("client_email", "").strip() or "(no client email set)"
        inv_num  = data["invoice_number"]
        EmailPreviewDialog(self, subject, to_email, body, inv_num,
                           send_callback=self._send_gmail)

    def _generate_ai_body(self):
        """Fill the email body textbox with the standard invoice template."""
        data = self._build_data()
        if not data:
            return
        s = self._get_settings()
        body_text = _invoice_email_template(data, s)
        self._email_body.delete("1.0", "end")
        self._email_body.insert("1.0", body_text)

    def _send_receipt(self):
        data = self._build_data()
        if not data:
            return
        s = self._get_settings()
        ReceiptDialog(self, data, s)


# ── Email preview dialog ──────────────────────────────────────────────────────

class EmailPreviewDialog(ctk.CTkToplevel):
    """Read-only preview of the invoice email — subject, body, attachment."""

    def __init__(self, parent, subject: str, to_email: str, body: str,
                 inv_num: str, send_callback):
        super().__init__(parent)
        self.title("Email Preview")
        self.geometry("600x560")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._send_callback = send_callback
        self._build_ui(subject, to_email, body, inv_num)

    def _build_ui(self, subject, to_email, body, inv_num):
        self.configure(fg_color="#f6f2ef")

        # Header
        top = ctk.CTkFrame(self, fg_color="#1c1917", corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Email Preview",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").pack(side="left", padx=20, pady=11)
        ctk.CTkLabel(top, text="exactly what gets sent",
                     font=ctk.CTkFont(size=10), text_color="#9e8e82").pack(
            side="left", padx=4)

        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=20, pady=(12, 4))
        pad.columnconfigure(1, weight=1)

        def meta_row(label, value, row, bold=False):
            ctk.CTkLabel(pad, text=label, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#5c5248", width=70).grid(
                row=row, column=0, sticky="nw", pady=(0, 6))
            ctk.CTkLabel(pad, text=value, anchor="w", wraplength=460,
                         font=ctk.CTkFont(size=11,
                                          weight="bold" if bold else "normal"),
                         text_color="#1c1917").grid(
                row=row, column=1, sticky="w", padx=(8, 0), pady=(0, 6))

        meta_row("To:",      to_email,  0)
        meta_row("Subject:", subject,   1, bold=True)

        # Attachment badge
        ctk.CTkLabel(pad, text="Attachment:", anchor="w",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#5c5248", width=70).grid(
            row=2, column=0, sticky="w", pady=(0, 10))
        att_frame = ctk.CTkFrame(pad, fg_color="#fff0f8", corner_radius=6)
        att_frame.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(0, 10))
        ctk.CTkLabel(att_frame,
                     text=f"📎  {inv_num}.pdf   (invoice generated automatically)",
                     font=ctk.CTkFont(size=10), text_color="#c4006e").pack(
            padx=10, pady=4)

        # Divider
        ctk.CTkFrame(pad, fg_color="#ddd6cf", height=1).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Body — editable so user can make last-second tweaks
        ctk.CTkLabel(pad, text="Body:", anchor="nw",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#5c5248", width=70).grid(
            row=4, column=0, sticky="nw")
        self._body_box = ctk.CTkTextbox(pad, corner_radius=6)
        self._body_box.grid(row=4, column=1, sticky="nsew", padx=(8, 0))
        self._body_box.insert("1.0", body)
        pad.rowconfigure(4, weight=1)

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="Send Now", width=130,
                      fg_color="#c4006e", hover_color="#8b004d",
                      command=self._send_now).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Close", width=90,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=6)

    def _send_now(self):
        self.destroy()
        self._send_callback()


# ── Receipt dialog ────────────────────────────────────────────────────────────

class ReceiptDialog(ctk.CTkToplevel):
    """Compose and send a Venmo payment-received confirmation email."""

    def __init__(self, parent, inv_data: dict, inv_settings: dict):
        super().__init__(parent)
        self.title("Send Payment Receipt")
        self.geometry("500x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        self._inv_data     = inv_data
        self._inv_settings = inv_settings
        self._receipt_path: str | None = None   # path to Venmo screenshot
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.configure(fg_color="#f6f2ef")

        # Header
        top = ctk.CTkFrame(self, fg_color="#b8882a", corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="Send Payment Receipt",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#1c1917").pack(side="left", padx=20, pady=11)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=12)
        body.columnconfigure(1, weight=1)

        row = [0]

        def lbl(text, r, c=0, **kw):
            ctk.CTkLabel(body, text=text, anchor="w",
                         font=ctk.CTkFont(size=11), **kw).grid(
                row=r, column=c, sticky="w", pady=(6, 1),
                padx=(0 if c == 0 else 8, 0))

        # Invoice # / Period (read-only info)
        lbl("Invoice", 0); lbl("Period", 0, 1)
        ctk.CTkLabel(body, text=self._inv_data["invoice_number"],
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#c4006e", anchor="w").grid(
            row=1, column=0, sticky="w", pady=(0, 6))
        ctk.CTkLabel(body, text=self._inv_data["period_label"],
                     font=ctk.CTkFont(size=12), text_color="#1c1917",
                     anchor="w").grid(row=1, column=1, sticky="w",
                                      padx=(8, 0), pady=(0, 6))

        # Payment date
        lbl("Payment Date", 2)
        pf = ctk.CTkFrame(body, fg_color="transparent")
        pf.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        pf.columnconfigure(0, weight=1)
        self._pay_date_var = tk.StringVar(value=date.today().isoformat())
        pay_ent = ctk.CTkEntry(pf, height=32, textvariable=self._pay_date_var)
        pay_ent.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(pf, text="📅", width=36, height=32,
                      fg_color="#c4006e", hover_color="#8b004d",
                      text_color="white", corner_radius=6,
                      command=lambda: CalendarPopup(
                          self, pay_ent,
                          date.today(),
                          lambda iso: self._pay_date_var.set(iso))
                      ).grid(row=0, column=1)

        # Amount
        lbl("Amount Received ($)", 4)
        self._amount_var = tk.StringVar(
            value=self._inv_settings.get("retainer_amount", "750.00"))
        ctk.CTkEntry(body, height=32, textvariable=self._amount_var).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        # Personal note (optional)
        lbl("Note to Client (optional)", 6)
        self._note = ctk.CTkTextbox(body, height=56, corner_radius=6)
        self._note.grid(row=7, column=0, columnspan=2,
                        sticky="ew", pady=(0, 6))

        # Venmo receipt file
        lbl("Venmo Receipt Screenshot / File", 8)
        att_row = ctk.CTkFrame(body, fg_color="transparent")
        att_row.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        att_row.columnconfigure(1, weight=1)
        ctk.CTkButton(att_row, text="Browse…", width=90, height=30,
                      fg_color="#1c1917", hover_color="#3a3230",
                      command=self._browse_receipt).grid(row=0, column=0,
                                                         padx=(0, 8))
        self._att_lbl = ctk.CTkLabel(att_row, text="No file selected",
                                     anchor="w", text_color="#5c5248",
                                     font=ctk.CTkFont(size=10))
        self._att_lbl.grid(row=0, column=1, sticky="w")

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=10)
        self._send_btn = ctk.CTkButton(
            btn_row, text="Send Confirmation", width=160,
            fg_color="#b8882a", hover_color="#c49830", text_color="#1c1917",
            command=self._send)
        self._send_btn.pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Cancel", width=90,
                      fg_color="#5c5248", hover_color="#3a3230",
                      command=self.destroy).pack(side="left", padx=6)

    def _browse_receipt(self):
        path = filedialog.askopenfilename(
            title="Select Venmo Receipt",
            filetypes=[
                ("Images & PDFs", "*.png *.jpg *.jpeg *.gif *.webp *.bmp *.pdf"),
                ("All files", "*.*"),
            ])
        if path:
            self._receipt_path = path
            self._att_lbl.configure(text=os.path.basename(path),
                                    text_color="#1c1917")

    # ── Send ──────────────────────────────────────────────────────────────────

    def _send(self):
        gmail_user = database.get_setting("gmail_address", "").strip()
        gmail_pass = database.get_setting("gmail_app_password", "").strip()
        client_email = self._inv_settings.get("client_email", "").strip()

        if not client_email:
            messagebox.showwarning("Missing Email",
                                   "No client email on the invoice.", parent=self)
            return
        if not gmail_user or not gmail_pass:
            messagebox.showinfo(
                "Gmail Not Configured",
                "Add your Gmail address and App Password in Settings.",
                parent=self)
            return

        try:
            pay_d = date.fromisoformat(self._pay_date_var.get())
            pay_date_str = pay_d.strftime("%B %d, %Y")
        except ValueError:
            pay_date_str = self._pay_date_var.get()

        amount   = self._amount_var.get().strip().lstrip("$") or \
                   self._inv_settings.get("retainer_amount", "750.00")
        inv_num  = self._inv_data["invoice_number"]
        period   = self._inv_data["period_label"]
        your_name = self._inv_settings.get("your_name", "")
        client_name = self._inv_settings.get("company_name", "")
        note_text = self._note.get("1.0", "end-1c").strip()

        subject = f"Payment Received — {inv_num} ({period})"
        body_lines = [
            f"Dear {client_name},",
            "",
            f"This is to confirm that I received your Venmo payment for invoice {inv_num}.",
            "",
            f"Invoice:         {inv_num}",
            f"Period:          {period}",
            f"Amount Received: ${amount}",
            f"Payment Date:    {pay_date_str}",
        ]
        if self._receipt_path:
            body_lines += ["",
                           "The Venmo receipt is attached for your records."]
        if note_text:
            body_lines += ["", note_text]
        body_lines += ["", "Thank you!", your_name]
        body = "\n".join(body_lines)

        self._send_btn.configure(state="disabled", text="Sending…")

        def do_send():
            try:
                _smtp_send(
                    gmail_user, gmail_pass, client_email,
                    subject, body,
                    pdf_path=None,
                    extra_attachments=[self._receipt_path] if self._receipt_path else None,
                )
                self.after(0, lambda: messagebox.showinfo(
                    "Sent!", f"Receipt confirmation sent to {client_email}.",
                    parent=self))
                self.after(0, self.destroy)
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror(
                    "Send Failed",
                    f"{e}\n\nCheck your Gmail credentials in Settings.",
                    parent=self))
            finally:
                self.after(0, lambda: self._send_btn.configure(
                    state="normal", text="Send Confirmation"))

        threading.Thread(target=do_send, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = TimeTrackerApp()
    app.mainloop()
