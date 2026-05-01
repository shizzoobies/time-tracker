"""
supabase_sync.py — Fire-and-forget Supabase sync module.
Uses only stdlib (urllib, json). Never raises — prints errors only.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uouikuifeherablbhzsy.supabase.co").rstrip("/")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_yQtGhRNiB8hmJ22hzfQSyQ_rK-ecV7G")

_TIMEOUT = 8  # seconds


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _request(method: str, path: str, body: dict | None = None,
             extra_headers: dict | None = None) -> dict | list | None:
    """Low-level request helper. Returns parsed JSON or None on error."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        print("[supabase_sync] SUPABASE_URL or SUPABASE_KEY not set — skipping sync")
        return None

    url = f"{_SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = _headers(extra_headers)

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
            if raw:
                return json.loads(raw)
            return None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"[supabase_sync] HTTP {e.code} on {method} {url}: {body_text}")
        return None
    except Exception as exc:
        print(f"[supabase_sync] Error on {method} {url}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Time Entries
# ---------------------------------------------------------------------------

def push_entry(entry: dict) -> None:
    """Upsert a time entry by local_id.

    entry keys expected: id (sqlite id), date, hours, description,
                         category, start_time, end_time, updated_at
    """
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "local_id":    entry.get("id"),
        "date":        entry.get("date"),
        "hours":       entry.get("hours"),
        "description": entry.get("description"),
        "category":    entry.get("category"),
        "start_time":  entry.get("start_time"),
        "end_time":    entry.get("end_time"),
        "updated_at":  entry.get("updated_at") or now,
        "created_at":  entry.get("created_at") or now,
    }
    _request(
        "POST",
        "time_entries?on_conflict=local_id",
        body=payload,
        extra_headers={"Prefer": "resolution=merge-duplicates"},
    )


def delete_entry(local_id: int) -> None:
    """Delete a time entry by local_id."""
    _request("DELETE", f"time_entries?local_id=eq.{local_id}")


def pull_new_entries() -> list[dict]:
    """Return entries where local_id IS NULL (created on iOS, not yet imported)."""
    result = _request("GET", "time_entries?local_id=is.null&order=created_at.asc")
    if isinstance(result, list):
        return result
    return []


def update_entry_local_id(supabase_uuid: str, local_id: int) -> None:
    """Set local_id on a Supabase row after desktop import."""
    _request(
        "PATCH",
        f"time_entries?id=eq.{supabase_uuid}",
        body={"local_id": local_id},
        extra_headers={"Prefer": "return=minimal"},
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def push_project(project: dict) -> None:
    """Upsert a project by local_id.

    project keys expected: id (sqlite id), name, description, priority,
                           status, completion, due_date, is_ongoing,
                           created_at, updated_at
    """
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "local_id":    project.get("id"),
        "name":        project.get("name"),
        "description": project.get("description"),
        "priority":    project.get("priority"),
        "status":      project.get("status"),
        "completion":  project.get("completion"),
        "due_date":    project.get("due_date"),
        "is_ongoing":  project.get("is_ongoing"),
        "updated_at":  project.get("updated_at") or now,
        "created_at":  project.get("created_at") or now,
    }
    _request(
        "POST",
        "projects?on_conflict=local_id",
        body=payload,
        extra_headers={"Prefer": "resolution=merge-duplicates"},
    )


def delete_project(local_id: int) -> None:
    """Delete a project by local_id."""
    _request("DELETE", f"projects?local_id=eq.{local_id}")


def pull_new_projects() -> list[dict]:
    """Return projects where local_id IS NULL (created on iOS, not yet imported)."""
    result = _request("GET", "projects?local_id=is.null&order=created_at.asc")
    if isinstance(result, list):
        return result
    return []


def update_project_local_id(supabase_uuid: str, local_id: int) -> None:
    """Set local_id on a Supabase project row after desktop import."""
    _request(
        "PATCH",
        f"projects?id=eq.{supabase_uuid}",
        body={"local_id": local_id},
        extra_headers={"Prefer": "return=minimal"},
    )
