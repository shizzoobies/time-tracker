import sqlite3
import os
import threading as _threading
from datetime import datetime

# ── Optional Supabase sync ────────────────────────────────────────────────────

try:
    import supabase_sync as _sync
    _SYNC_AVAILABLE = True
except ImportError:
    _sync = None  # type: ignore
    _SYNC_AVAILABLE = False


def _bg(fn, *args, **kwargs):
    """Fire a function in a daemon background thread. No-ops if sync unavailable."""
    if not _SYNC_AVAILABLE:
        return
    t = _threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


# ── DB setup ──────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'timetracker.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                priority TEXT DEFAULT 'Medium',
                status TEXT DEFAULT 'Active',
                completion INTEGER DEFAULT 0,
                due_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS time_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                hours REAL NOT NULL,
                description TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                start_time TEXT,
                end_time TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        _migrate_db(conn)
        defaults = {
            'your_name': 'Alexander Anderson',
            'company_name': 'PB&J Strategic Accounting',
        }
        for key, value in defaults.items():
            conn.execute(
                'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                (key, value)
            )
        conn.commit()


def _migrate_db(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(time_entries)").fetchall()}
    if 'start_time' not in cols:
        conn.execute("ALTER TABLE time_entries ADD COLUMN start_time TEXT")
    if 'end_time' not in cols:
        conn.execute("ALTER TABLE time_entries ADD COLUMN end_time TEXT")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if 'is_ongoing' not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN is_ongoing INTEGER DEFAULT 0")


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, default=''):
    with get_connection() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else default


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()


# ── Time Entries ──────────────────────────────────────────────────────────────

def add_entry(date, hours, description, category, start_time=None, end_time=None):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            'INSERT INTO time_entries (date, hours, description, category, start_time, end_time, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (date, hours, description, category, start_time, end_time, now, now)
        )
        conn.commit()
        new_id = cur.lastrowid
    _bg(_sync.push_entry, {
        'id': new_id, 'date': date, 'hours': hours, 'description': description,
        'category': category, 'start_time': start_time, 'end_time': end_time,
        'created_at': now, 'updated_at': now,
    })
    return new_id


def update_entry(entry_id, date, hours, description, category, start_time=None, end_time=None):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            'UPDATE time_entries SET date=?, hours=?, description=?, category=?, start_time=?, end_time=?, updated_at=? WHERE id=?',
            (date, hours, description, category, start_time, end_time, now, entry_id)
        )
        conn.commit()
    _bg(_sync.push_entry, {
        'id': entry_id, 'date': date, 'hours': hours, 'description': description,
        'category': category, 'start_time': start_time, 'end_time': end_time,
        'updated_at': now,
    })


def delete_entry(entry_id):
    with get_connection() as conn:
        conn.execute('DELETE FROM time_entries WHERE id=?', (entry_id,))
        conn.commit()
    _bg(_sync.delete_entry, entry_id)


def get_entries_for_week(week_start, week_end):
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM time_entries WHERE date >= ? AND date <= ? ORDER BY date ASC, created_at ASC',
            (week_start, week_end)
        ).fetchall()
        return [dict(row) for row in rows]


def get_entry(entry_id):
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM time_entries WHERE id=?', (entry_id,)).fetchone()
        return dict(row) if row else None


# ── Projects ──────────────────────────────────────────────────────────────────

_PRIORITY_ORDER = "CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END"
_STATUS_ORDER   = "CASE status WHEN 'Active' THEN 1 WHEN 'On Hold' THEN 2 ELSE 3 END"


def get_projects():
    with get_connection() as conn:
        rows = conn.execute(
            f'SELECT * FROM projects ORDER BY {_STATUS_ORDER}, {_PRIORITY_ORDER}, name'
        ).fetchall()
        return [dict(r) for r in rows]


def get_project(project_id):
    with get_connection() as conn:
        row = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        return dict(row) if row else None


def add_project(name, description='', priority='Medium', status='Active',
                completion=0, due_date=None, is_ongoing=0):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            'INSERT INTO projects (name, description, priority, status, completion, due_date, is_ongoing, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (name, description, priority, status, completion, due_date, is_ongoing, now, now)
        )
        conn.commit()
        new_id = cur.lastrowid
    _bg(_sync.push_project, {
        'id': new_id, 'name': name, 'description': description, 'priority': priority,
        'status': status, 'completion': completion, 'due_date': due_date,
        'is_ongoing': is_ongoing, 'created_at': now, 'updated_at': now,
    })
    return new_id


def update_project(project_id, name, description='', priority='Medium',
                   status='Active', completion=0, due_date=None, is_ongoing=0):
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            'UPDATE projects SET name=?, description=?, priority=?, status=?, completion=?, due_date=?, is_ongoing=?, updated_at=? WHERE id=?',
            (name, description, priority, status, completion, due_date, is_ongoing, now, project_id)
        )
        conn.commit()
    _bg(_sync.push_project, {
        'id': project_id, 'name': name, 'description': description, 'priority': priority,
        'status': status, 'completion': completion, 'due_date': due_date,
        'is_ongoing': is_ongoing, 'updated_at': now,
    })


def delete_project(project_id):
    with get_connection() as conn:
        conn.execute('DELETE FROM projects WHERE id=?', (project_id,))
        conn.commit()
    _bg(_sync.delete_project, project_id)


# ── Supabase cloud sync ───────────────────────────────────────────────────────

def sync_from_cloud():
    """Pull iOS-created entries/projects (local_id IS NULL) and import them to SQLite."""
    if not _SYNC_AVAILABLE:
        print("[sync] supabase_sync not available — install python-dotenv and ensure .env is loaded")
        return 0, 0

    # ---- entries ----
    entries = _sync.pull_new_entries()
    imported_entries = 0
    for row in entries:
        try:
            new_id = add_entry(
                date=row.get("date", ""),
                hours=float(row.get("hours", 0)),
                description=row.get("description", ""),
                category=row.get("category", "General"),
                start_time=row.get("start_time"),
                end_time=row.get("end_time"),
            )
            if new_id:
                _sync.update_entry_local_id(row["id"], new_id)
                imported_entries += 1
        except Exception as exc:
            print(f"[sync] Failed to import entry {row.get('id')}: {exc}")

    # ---- projects ----
    projects = _sync.pull_new_projects()
    imported_projects = 0
    for row in projects:
        try:
            new_id = add_project(
                name=row.get("name", ""),
                description=row.get("description", ""),
                priority=row.get("priority", "Medium"),
                status=row.get("status", "Active"),
                completion=int(row.get("completion") or 0),
                due_date=row.get("due_date"),
                is_ongoing=int(row.get("is_ongoing") or 0),
            )
            if new_id:
                _sync.update_project_local_id(row["id"], new_id)
                imported_projects += 1
        except Exception as exc:
            print(f"[sync] Failed to import project {row.get('id')}: {exc}")

    print(f"[sync] Imported {imported_entries} entries, {imported_projects} projects from cloud")
    return imported_entries, imported_projects


# ── Invoice helpers ───────────────────────────────────────────────────────────

def get_hours_in_period(start_date: str, end_date: str) -> float:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT COALESCE(SUM(hours), 0) FROM time_entries WHERE date >= ? AND date <= ?',
            (start_date, end_date)
        ).fetchone()
        return float(row[0])


def get_total_hours_up_to(end_date: str) -> float:
    with get_connection() as conn:
        row = conn.execute(
            'SELECT COALESCE(SUM(hours), 0) FROM time_entries WHERE date <= ?',
            (end_date,)
        ).fetchone()
        return float(row[0])
