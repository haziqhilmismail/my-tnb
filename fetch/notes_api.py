"""Tiny write API for notes. The page reads data/notes.json directly; this only saves.

A note covers a span of days, and notes may overlap:
    {"id": "a1b2c3d4", "from": "2026-09-25", "to": null, "text": "balik kampung"}
`to` is null while the note is still ongoing.

POST /api/notes  {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD" | null, "text": "..."}   adds a note
POST /api/notes  {"id": "...", "from": ..., "to": ..., "text": "..."}              changes that note
POST /api/notes  {"id": "...", "text": ""}                                         deletes it
Every call answers with the full list.

POST /api/fetch  (no body)  asks the fetch container to pull from TNB now.

A POST from another site (its Origin header names a different host) gets 403, and
/api/notes accepts only Content-Type: application/json, so other pages cannot write.
"""

import json
import threading
import time
import uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from paths import FETCH_REQUEST, NOTES_FILE

MAX_BODY_BYTES = 2048
MAX_NOTE_CHARS = 200
MAX_NOTES = 1000
# The page has no login, so this stops anyone from hammering TNB's login through the button
FETCH_COOLDOWN_SECONDS = 300
write_lock = threading.Lock()

Note = dict[str, str | None]


def parse_day(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("dates must be strings")
    parsed = date.fromisoformat(value)  # raises ValueError on a non-date
    if parsed.isoformat() != value:
        raise ValueError("dates must be YYYY-MM-DD")
    return parsed


def apply_note(notes: list[Note], payload: object, new_id: str) -> list[Note]:
    """Return notes with the payload applied. Raises ValueError on bad input."""
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    note_id, text = payload.get("id"), payload.get("text")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if note_id is not None and not any(n["id"] == note_id for n in notes):
        raise ValueError("no note with that id")
    others = [n for n in notes if n["id"] != note_id]
    text = text.strip()
    if not text:
        if note_id is None:
            raise ValueError("the note is empty")
        return others
    if len(text) > MAX_NOTE_CHARS:
        raise ValueError(f"note is longer than {MAX_NOTE_CHARS} characters")
    if len(others) >= MAX_NOTES:
        raise ValueError(f"there are already {MAX_NOTES} notes")
    start = parse_day(payload.get("from"))
    end = None if payload.get("to") is None else parse_day(payload["to"])
    if end is not None and end < start:
        raise ValueError("the end date is before the start date")
    note = {"id": note_id or new_id, "from": start.isoformat(), "to": end and end.isoformat(), "text": text}
    return sorted([*others, note], key=lambda n: (n["from"], n["id"]))


def fetch_wait(last_request: float | None, now: float) -> float:
    """Seconds left before another fetch may be asked for. 0 or less means go ahead."""
    return 0 if last_request is None else FETCH_COOLDOWN_SECONDS - (now - last_request)


def same_origin(origin: str | None, host: str | None) -> bool:
    """Browsers send Origin on every POST. No Origin means curl or a script, which the page has no login to stop anyway."""
    return origin is None or urlsplit(origin).netloc == host


def load_notes() -> list[Note]:
    try:
        notes = json.loads(NOTES_FILE.read_text())
    except FileNotFoundError:
        return []
    if not isinstance(notes, list) or not all(isinstance(n, dict) and "id" in n for n in notes):
        raise RuntimeError(f"{NOTES_FILE} is not a list of notes")
    return notes


def save_notes(notes: list[Note]) -> None:
    # Temp file first so the page never reads a half-written file
    tmp = NOTES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(notes, indent=1))
    tmp.replace(NOTES_FILE)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def request_fetch(self) -> None:
        with write_lock:
            last = FETCH_REQUEST.stat().st_mtime if FETCH_REQUEST.exists() else None
            wait = fetch_wait(last, time.time())
            if wait > 0:
                minutes = int(wait // 60) + 1
                return self.reply(429, {"error": f"Asked a moment ago. Try again in {minutes} min."})
            FETCH_REQUEST.touch()
        self.reply(202, {"ok": True})

    def do_POST(self) -> None:
        if not same_origin(self.headers.get("Origin"), self.headers.get("Host")):
            return self.reply(403, {"error": "cross-site request"})
        if self.path == "/api/fetch":
            return self.request_fetch()
        if self.path != "/api/notes":
            return self.reply(404, {"error": "not found"})
        if self.headers.get_content_type() != "application/json":
            return self.reply(415, {"error": "Content-Type must be application/json"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.reply(400, {"error": "bad Content-Length"})
        if not 0 < length <= MAX_BODY_BYTES:
            return self.reply(413, {"error": "body missing or too large"})
        try:
            payload = json.loads(self.rfile.read(length))
            with write_lock:
                notes = apply_note(load_notes(), payload, uuid.uuid4().hex[:8])
                save_notes(notes)
        except ValueError as err:  # includes json.JSONDecodeError
            return self.reply(400, {"error": str(err)})
        except RuntimeError as err:
            return self.reply(500, {"error": str(err)})
        self.reply(200, notes)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
