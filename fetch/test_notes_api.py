"""Run with: python test_notes_api.py"""

from datetime import date

from notes_api import FETCH_COOLDOWN_SECONDS, MAX_NOTE_CHARS, apply_note, fetch_wait, migrate

# add
notes = apply_note([], {"from": "2026-09-25", "to": None, "text": "  mama abah balik kampung  "}, "aaa")
assert notes == [{"id": "aaa", "from": "2026-09-25", "to": None, "text": "mama abah balik kampung"}], notes

# a second note may overlap the first: both are kept
notes = apply_note(notes, {"from": "2026-09-26", "to": "2026-09-26", "text": "kenduri"}, "bbb")
assert [n["id"] for n in notes] == ["aaa", "bbb"], notes

# change by id keeps the id, delete by id removes only that note
ended = apply_note(notes, {"id": "aaa", "from": "2026-09-25", "to": "2026-10-10", "text": "balik kampung"}, "unused")
assert ended[0] == {"id": "aaa", "from": "2026-09-25", "to": "2026-10-10", "text": "balik kampung"}, ended
assert [n["id"] for n in apply_note(notes, {"id": "aaa", "text": ""}, "unused")] == ["bbb"]

bad_payloads = [
    [],
    {"from": "2026-09-11", "to": None},
    {"from": "2026-09-11", "to": None, "text": ""},
    {"from": "2026-09-11", "to": "2026-09-10", "text": "x"},
    {"from": "11/09/2026", "to": None, "text": "x"},
    {"from": "2026-13-01", "to": None, "text": "x"},
    {"from": "20260911", "to": None, "text": "x"},
    {"from": "2026-09-11", "to": "soon", "text": "x"},
    {"from": "2026-09-11", "to": None, "text": "x" * (MAX_NOTE_CHARS + 1)},
    {"from": "2026-09-11", "to": None, "text": 5},
    {"id": "nope", "from": "2026-09-11", "to": None, "text": "x"},
]
for bad in bad_payloads:
    try:
        apply_note(notes, bad, "ccc")
    except ValueError:
        continue
    raise AssertionError(f"accepted bad payload: {bad!r}")

# old one-note-per-day file: runs of the same text merge, a run past today becomes ongoing
old = {"2026-09-06": "a", "2026-09-15": "b", "2026-09-16": "b", "2026-09-25": "b", "2026-09-26": "b", "2027-09-25": "b"}
old |= {f"2026-{m:02d}-{d:02d}": "b" for m in (9, 10) for d in range(27 if m == 9 else 1, 31)}
spans = [(n["from"], n["to"], n["text"]) for n in migrate(old, date(2026, 10, 5))]
assert spans[:3] == [("2026-09-06", "2026-09-06", "a"), ("2026-09-15", "2026-09-16", "b"), ("2026-09-25", None, "b")], spans
full = {f"2026-{m:02d}-{d:02d}": "b" for m, last in ((9, 30), (10, 31)) for d in range(25 if m == 9 else 1, last + 1)}
assert [(n["from"], n["to"]) for n in migrate(full, date(2026, 10, 5))] == [("2026-09-25", None)]

# fetch button: allowed the first time and after the cooldown, refused in between
assert fetch_wait(None, 1000) <= 0
assert fetch_wait(1000, 1000 + FETCH_COOLDOWN_SECONDS - 1) > 0
assert fetch_wait(1000, 1000 + FETCH_COOLDOWN_SECONDS) <= 0

print("ok")
