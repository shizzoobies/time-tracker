import anthropic
import json
from datetime import date

from constants import CATEGORIES

_client_cache: dict[str, anthropic.Anthropic] = {}


def _get_client(api_key: str) -> anthropic.Anthropic:
    if api_key not in _client_cache:
        _client_cache[api_key] = anthropic.Anthropic(api_key=api_key)
    return _client_cache[api_key]


def parse_time_entries(text: str, api_key: str, current_date: str = None) -> list[dict]:
    """Parse natural language into one or more time entries. Always returns a list."""
    if not api_key:
        raise ValueError("No API key configured. Please set your Anthropic API key in Settings.")

    if current_date is None:
        current_date = date.today().isoformat()

    client = _get_client(api_key)

    prompt = f"""Today's date is {current_date}.

Parse this time tracking input and return ONLY a JSON array of entry objects (no markdown, no explanation).
Even if there is just one entry, return an array with one element.
If the input describes multiple tasks or spreading work across multiple days/times, create one entry per slot.

"{text}"

Each entry object must have:
- date: ISO date YYYY-MM-DD (infer from "today", "yesterday", "this morning", day names, "Saturday", "Sunday", etc.)
- start_time: 24-hour HH:MM — if not stated but you are creating a spread of entries, assign a realistic start time (e.g. 09:00, 10:00, 13:00, 14:00). Never leave null when you are generating multiple entries across days.
- end_time: 24-hour HH:MM — derive from start_time + hours. Never leave null when you have a start_time.
- hours: decimal — compute from start/end if both given; if the user specifies session lengths (e.g. "1-3 hour increments", "2 hours at a time"), use those as the per-entry hours and create as many entries as needed to reach any stated total; otherwise split evenly
- description: concise task description
- category: one of {json.dumps(CATEGORIES)}

Examples:
Single: [{{"date": "2024-01-15", "start_time": "09:00", "end_time": "11:30", "hours": 2.5, "description": "Payroll reconciliation", "category": "Administrative"}}]
Multiple: [{{"date": "2024-01-20", "start_time": null, "end_time": null, "hours": 2.0, "description": "SEO audit", "category": "SEO Audit"}}, {{"date": "2024-01-21", "start_time": null, "end_time": null, "hours": 2.0, "description": "SEO audit continued", "category": "SEO Audit"}}]"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    result = None
    if "```" in response_text:
        for part in response_text.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                result = json.loads(part)
                break
            except json.JSONDecodeError:
                continue

    if result is None:
        result = json.loads(response_text)

    # Normalise: accept a bare dict (single entry) too
    if isinstance(result, dict):
        result = [result]

    required = {"date", "hours", "description", "category"}
    cleaned = []
    for entry in result:
        missing = required - entry.keys()
        if missing:
            raise ValueError(f"AI response entry missing fields: {missing}")
        entry["hours"] = float(entry["hours"])
        entry.setdefault("start_time", None)
        entry.setdefault("end_time", None)
        cleaned.append(entry)

    return cleaned


# Keep old name as alias so nothing else breaks
def parse_time_entry(text: str, api_key: str, current_date: str = None) -> dict:
    return parse_time_entries(text, api_key, current_date)[0]
