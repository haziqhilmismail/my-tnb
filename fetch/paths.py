"""Files shared by the fetch and notes containers through the /data volume."""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
HISTORY_FILE = DATA_DIR / "tnb_history.json"
NOTES_FILE = DATA_DIR / "notes.json"
# notes_api.py touches this file when the page asks for a fetch; tnb_daily.py watches its modified time
FETCH_REQUEST = DATA_DIR / "fetch_request"
