<p align="center"><img src="site/logo.svg" width="96" alt="Rumah Power Log logo"></p>

# Rumah Power Log

A small dashboard for the electricity use of one house. It pulls daily smart-meter
readings from myTNB every 6 hours. It shows cost, use, the weekday pattern and the bill history.

Live at **https://tnb.haziqhilmi.com** (no login). The name points to a private
address, so the page opens only on the home network or through Tailscale. A
reverse proxy on the server, outside this repo, sends the name to port 8085.
The page answers only to the names in `SITE_HOSTS`.

## How it works

```
        every 6 hours
myTNB  ───────────────►  fetch container  ──►  site/data/tnb_history.json
(TNB's servers)          (tnb_daily.py)   └─►  backups/  (one copy a day)
                                                       │
browser  ◄──────────────  web container  ◄─────────────┘
                          (Caddy, port 8085, serves site/)
```

Docker Compose runs three containers (see `docker-compose.yml`):

| Container | Job |
|---|---|
| `web` | Caddy. Serves the `site/` folder on port 8085 and sends `/api/*` to `notes` (see `Caddyfile`). |
| `fetch` | Python loop. Runs `mytnb usage <account> --json` and merges the result into the JSON file. |
| `notes` | Small Python server. Saves the day notes from the page into `site/data/notes.json`. |

There is no database. The page is one HTML file. It reads `data/tnb_history.json`
and `data/notes.json` directly. The write endpoints are `POST /api/notes` and `POST /api/fetch`.

The data comes from [python-mytnb](https://pypi.org/project/python-mytnb/), an
unofficial client for the feed that the myTNB app uses.

### Fetch now button

The button in the header calls `POST /api/fetch`. The `notes` container touches
`site/data/fetch_request`. The `fetch` container checks that file every 2 seconds
and runs early when it changes. The page then reloads the data until `updated`
changes. The server refuses a second press within 5 minutes. The page has no login,
so this stops people from sending many logins to TNB through the page.

### Why the data is merged, not replaced

TNB returns only about the last 30 days. Each run merges those days into the saved
file by date. The merge adds new dates, overwrites existing dates, and keeps older dates.
So the history grows past 30 days while the fetcher runs.

If the fetcher is off for more than 30 days, the days between are lost. TNB
does not serve them again.

## Set up

On a machine with Docker:

```bash
cp .env.example .env
chmod 600 .env
# fill in MYTNB_EMAIL, MYTNB_PASSWORD, MYTNB_ACCOUNT in .env
mkdir -p site/data backups
docker compose up -d --build
```

Environment variables (in `.env`):

| Name | Meaning |
|---|---|
| `MYTNB_EMAIL` | myTNB login email |
| `MYTNB_PASSWORD` | myTNB password, in single quotes |
| `MYTNB_ACCOUNT` | TNB account number. For more than one account, separate the numbers with commas. |
| `FETCH_INTERVAL_HOURS` | Hours between two fetches. Default `6`. |
| `SITE_HOSTS` | Host names and IPs the page answers to, separated by spaces, in double quotes. Caddy replies 421 to any other name. Default `localhost`. |

To find the account number, install the tool and list the accounts:

```bash
pip install "python-mytnb[cli]"
mytnb -e you@example.com -p 'password' accounts
```

The `fetch` and `notes` containers run as user `1000:1000` (set in
`docker-compose.yml`), so the files they write belong to the normal user. On
another machine, run `id -u`. If the result is not 1000, change those lines.

## Folder layout

```
my-tnb/
├── docker-compose.yml   all three containers
├── Caddyfile            web server config: static files + /api/* to notes
├── .env                 TNB login + account number (secret, not in git)
├── .env.example         template for .env
├── fetch/
│   ├── Dockerfile       python + python-mytnb
│   ├── paths.py         data file paths that both containers use
│   ├── tnb_daily.py     fetch, merge, backup loop
│   ├── notes_api.py     saves day notes (POST /api/notes)
│   ├── test_tnb_daily.py   tests for the TNB feed parser and the merge
│   └── test_notes_api.py   tests for the notes API
├── site/
│   ├── index.html       the whole dashboard (HTML + CSS + JS in one file)
│   ├── logo.svg         logo and favicon
│   ├── og.png, apple-touch-icon.png   link preview and home screen icon
│   ├── fonts/           IBM Plex (SIL Open Font License, see OFL.txt), served locally
│   └── data/            (not in git)
│       ├── tnb_history.json   the data, written by the fetch container
│       └── notes.json         day notes, written by the notes container
└── backups/             (not in git) dated copies of both files, newest 30 of each kept
```

## Data format

`site/data/tnb_history.json`:

```json
{
  "accounts": {
    "<account number>": {
      "name": "",
      "days":   { "2026-09-06": { "kwh": 20.0, "rm": 5.41, "est": false } },
      "months": { "2026-09-22": { "rm": 548.4, "kwh": 1064.0, "start": "2026-08-23", "unbilled": false,
                                  "parts": { "energy": 287.6, "capacity": 48.41, "network": 136.72, "customer": 10.0 } } },
      "summary": { "current_kwh": 334.0, "current_rm": 78.26, "projected_rm": 394.16, "cycle_start": "23/09/2026" },
      "updated": "2026-10-04T16:23:00+00:00"
    }
  }
}
```

- `days`: one entry for each day. `est` means that TNB estimated the reading.
- `months`: one entry for each bill cycle, with the end date of the cycle as the key.
  The open cycle has `unbilled: true`. Each fetch replaces it.
- `parts`: the bill split by the per-kWh rates that TNB publishes. The remainder of
  `rm` is fuel adjustment, tax and levies. The page calculates it.
  Bills older than the usage feed (from `mytnb bill-history`) have `rm` only.
- `summary`: the numbers from TNB for the current cycle.

## Notes

A note covers one day or a range of days. Notes can overlap: "balik kampung"
from 25 Sep and "kenduri" on 26 Sep can both exist.

- **Add, on a phone:** tap the daily chart, or move a finger along it. A one-day
  cursor follows the finger and the tooltip stays above it. When you lift the
  finger, the page selects that day. The arrows in the note dialog move the
  selection one day left or right, because a bar is only about 10px wide on a phone.
  For more than one day, set the From and To dates.
- **Add, with a mouse:** click a bar, or drag across bars for a range.
- A selection always starts a new note, even on days that already have one.
- **Change or delete:** tap the entry of the note in the dialog ("... · Edit"), or
  its line above the chart. Delete asks for confirmation.
- When you change the From / To dates, the highlight on the chart moves immediately.
- **Still ongoing:** select it when there is no end date yet. The note then runs up
  to today, every day, until you set an end date.
- **Use comparison:** the form shows the average kWh a day on the selected days
  against all other days, for example "27% below".
- **Bill History:** a bill bar gets a dot when notes fall inside its cycle. Its
  tooltip lists them with the number of days.

The page draws each note as a line over its days. On a wide screen, each note gets
its full label, and notes that collide stack in rows. On a phone, the page draws a
label only when it fits on its own line. The other notes stay as plain lines, and
the tooltip and the note dialog show their names.

`site/data/notes.json` is a list:

```json
[
  { "id": "b0771c63", "from": "2026-09-25", "to": null, "text": "Balik kampung" },
  { "id": "1f9c2e4a", "from": "2026-09-26", "to": "2026-09-26", "text": "Kenduri" }
]
```

`to` is `null` while a note is ongoing. A note has a maximum of 200 characters, and
the file a maximum of 1000 notes. There is no login: all people who can open the
page can add, change or delete notes. The API refuses a POST from another web
site (403) and a notes body that is not `application/json` (415). So a page on the
internet cannot write notes or start a fetch through the browser of a visitor.

```bash
# add
curl -X POST http://localhost:8085/api/notes -H 'Content-Type: application/json' \
  -d '{"from": "2026-09-26", "to": "2026-09-26", "text": "kenduri"}'
# change: same body plus "id".  delete: {"id": "...", "text": ""}
```

## How the page calculates cost

The daily `rm` from TNB is the energy charge only, about half of the real bill. So
the page does not use it. It estimates the cost instead:

```
daily cost = kWh that day × (RM of the last bill ÷ kWh of the last bill)
```

That rate includes network, capacity, tax and the fixed fee. It is one flat rate, so
it changes a little when use moves across the 600 kWh tax threshold. "Projected
bill" is the number from TNB, without changes.

"This cycle vs last" needs the daily readings of the previous cycle. Where they are
missing, the page fills the gap from the known total of that cycle and draws a dotted line.

## Common tasks

Run all of these on the server, in the `my-tnb` folder.

| Task | Command |
|---|---|
| See if it runs | `docker compose ps` |
| See fetch logs | `docker compose logs --tail 20 fetch` |
| Fetch now | press "Fetch now" on the page, or `docker compose restart fetch` |
| Stop everything | `docker compose down` |
| Start everything | `docker compose up -d` |
| Apply a change to `tnb_daily.py` | `docker compose up -d --build fetch` |
| Apply a change to `notes_api.py` | `docker compose up -d --build notes` |
| Apply a change to `paths.py` | `docker compose up -d --build fetch notes` |
| Apply a change to `SITE_HOSTS` | `docker compose up -d web` |
| Run the tests | `cd fetch && python test_tnb_daily.py && python test_notes_api.py` |
| Apply a change to `Caddyfile` | `docker compose restart web` |
| Apply a change to `index.html` | nothing, refresh the browser |

The web server sends `Cache-Control: no-cache`. So browsers check the page again on
each load and get a new `index.html` without a hard refresh.

A correct fetch log line looks like this (the last 4 digits of the account number come first):

```
1234: fetched 30 days, 58 saved in total
```

### Change how often it fetches

Edit `FETCH_INTERVAL_HOURS` in `.env`, then run `docker compose up -d fetch`.

The page marks the data as old after 13 hours (`STALE_MS` in `index.html`). If you
fetch less often than every 6 hours, make that number larger too.

### Add a second TNB account

Put both numbers in `.env`, with a comma between them:

```
MYTNB_ACCOUNT=220000000001,220000000002
```

Then run `docker compose up -d fetch`. When there is more than one account, the
page shows an account dropdown.

### Change the TNB password

Edit `MYTNB_PASSWORD` in `.env`, then run `docker compose up -d fetch`.
Keep the value in single quotes, so special characters stay as they are.

### Restore a backup

```bash
cp backups/tnb_history-2026-10-04.json site/data/tnb_history.json
cp backups/notes-2026-10-04.json site/data/notes.json   # notes, if necessary
```

Backup file names use the UTC date, so they can be one day behind Malaysia time.

## Deploy changes from another computer

Edit the source on a laptop, then copy it to the server with rsync. The command
excludes `.env` and the data folders, so it never overwrites the secrets or the live data on the server:

```bash
rsync -a --exclude .env --exclude .git --exclude site/data --exclude backups \
	--exclude .DS_Store --exclude __pycache__ ~/my-tnb/ server:my-tnb/
```

`server` is an SSH shortcut (`Host` entry in `~/.ssh/config`) for the server.

## Troubleshooting

| Symptom | Probable cause | Fix |
|---|---|---|
| Header pill is amber, "Last update ..." | fetch container stopped, or the TNB login fails | `docker compose logs --tail 20 fetch` |
| Log says `mytnb failed: ...` | wrong password, or the TNB API is down | check `.env`, try again later |
| Log says `update failed: JSONDecodeError` | `tnb_history.json` is corrupt | restore a backup (see above) |
| Page says "Can't reach the server" | `web` container is down, or the data file is missing | `docker compose up -d` |
| Bill history card is empty | the data file is from before bills were added | `docker compose restart fetch` |

When the data file is corrupt, the fetcher stops writes on purpose. A fresh start
would replace the full history with only the last 30 days.

## Known limits

- **Unofficial source.** `python-mytnb` uses the same feed as the myTNB app.
  TNB can change it at any time and break the fetcher. `fetch/Dockerfile` pins the version.
- **Daily cost is an estimate.** See "How the page calculates cost". The
  Bill history card shows the real billed amounts.
- **Backups are on the same disk** as the live file. They protect against a bad
  write, not against a disk failure.
- **No login on the page.** All people on the home network or the tailnet can open it.
  It is not on the public internet. The API blocks cross-site writes, but not a
  person who opens the page.
- **The link preview has a fixed address.** `og:url` and `og:image` in
  `site/index.html` point to `https://tnb.haziqhilmi.com`. If the name changes,
  update those two lines.
- **Daily history starts on 6 Sep 2026.** That was the earliest day that TNB still
  served when this was set up.
