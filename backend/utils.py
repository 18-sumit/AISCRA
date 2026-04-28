"""backend/utils.py — shared serialization helpers."""

def utc_iso(dt) -> str | None:
    """
    Serialize a datetime to ISO-8601 with explicit Z suffix.
    SQLite stores naive UTC datetimes — appending Z tells JS to parse as UTC,
    not local time. Without this, IST users see timestamps 5.5h in the past.
    """
    if dt is None:
        return None
    s = dt.isoformat()
    # Only append Z if no timezone info already present
    if dt.tzinfo is None and not s.endswith('Z') and '+' not in s:
        s += 'Z'
    return s
