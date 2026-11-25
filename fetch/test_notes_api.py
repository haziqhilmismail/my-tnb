"""Run with: python test_notes_api.py"""

from notes_api import FETCH_COOLDOWN_SECONDS, MAX_NOTE_CHARS, apply_note, fetch_wait, same_origin

# add
notes = apply_note([], {"from": "2026-09-25", "to": None, "text": "  balik kampung  "}, "aaa")
assert notes == [{"id": "aaa", "from": "2026-09-25", "to": None, "text": "balik kampung"}], notes

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

# fetch button: allowed the first time and after the cooldown, refused in between
assert fetch_wait(None, 1000) <= 0
assert fetch_wait(1000, 1000 + FETCH_COOLDOWN_SECONDS - 1) > 0
assert fetch_wait(1000, 1000 + FETCH_COOLDOWN_SECONDS) <= 0

assert same_origin("https://tnb.example.com", "tnb.example.com")
assert same_origin("http://192.0.2.10:8085", "192.0.2.10:8085")
assert same_origin(None, "tnb.example.com")
assert not same_origin("https://evil.example", "tnb.example.com")
assert not same_origin("null", "tnb.example.com")
assert not same_origin("http://192.0.2.10:9999", "192.0.2.10:8085")

print("ok")
