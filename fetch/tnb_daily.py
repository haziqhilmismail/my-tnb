"""Fetch daily smart-meter usage from myTNB and merge it into tnb_history.json.

TNB's feed only covers the last few weeks, so each run merges new days into the
saved history instead of replacing it. Runs forever, once every FETCH_INTERVAL_HOURS,
and straight away when the page's "Fetch now" button is pressed.
"""

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from paths import FETCH_REQUEST, HISTORY_FILE, NOTES_FILE

INTERVAL_SECONDS = float(os.environ.get("FETCH_INTERVAL_HOURS", "6")) * 3600
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backups"))
BACKUP_KEEP = 30
# TNB rate id -> name used in the saved file
PER_KWH_CHARGES = {"EnergyCharge": "energy", "CapacityCharge": "capacity", "NetworkCharge": "network"}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def num(value: object) -> float | None:
    """'RM 12.50' -> 12.5, anything unparseable -> None."""
    if value is None:
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(value)))
    except ValueError:
        return None


def iso_date(day: dict) -> str | None:
    month = str(day.get("month", "")).strip()
    month_no = int(month) if month.isdigit() else MONTHS.get(month[:3].lower())
    try:
        return f"{int(day['year']):04d}-{month_no:02d}-{int(day['day']):02d}"
    except (KeyError, TypeError, ValueError):
        return None


def metric(metrics: list[dict], key: str) -> float | None:
    return next((num(m.get("value")) for m in metrics if m.get("key") == key), None)


def mytnb(command: str, account: str) -> dict | list:
    """Login comes from MYTNB_EMAIL / MYTNB_PASSWORD in the environment."""
    result = subprocess.run(
        ["mytnb", command, account, "--json"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    return json.loads(result.stdout)


def parse_days(usage: dict) -> dict[str, dict]:
    days = {}
    for week in usage.get("by_day", []):
        for day in week.get("days", []):
            if day.get("is_missing_reading"):
                continue
            date = iso_date(day)
            kwh, rm = num(day.get("consumption")), num(day.get("amount"))
            if date is None or (kwh is None and rm is None):
                continue
            days[date] = {"kwh": kwh, "rm": rm, "est": bool(day.get("is_estimated_reading"))}
    return days


def parse_months(usage: dict) -> dict[str, dict]:
    """Bill cycles keyed by their end date. TNB sends dates as 'YYYYMMDD'."""
    def iso(compact: str) -> str:
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"

    feed = usage.get("by_month", {}).get("months", [])
    # TNB sends one rate table per month, in the same order as the months
    rate_tables = usage.get("tariff_blocks_legend_rp4", [])
    if len(rate_tables) != len(feed):
        rate_tables = [{}] * len(feed)

    months = {}
    for month, table in zip(feed, rate_tables):
        start, end = month.get("billing_start_date"), month.get("billing_end_date")
        if not start or not end:
            continue
        kwh, unbilled = num(month.get("usage_total")), bool(month.get("is_unbilled"))
        cycle = {"rm": num(month.get("amount_total")), "kwh": kwh, "start": iso(start), "unbilled": unbilled}
        rates = {item["block_id"]: num(item.get("block_price")) for item in table.get("items", [])}
        if not unbilled and kwh and all(rates.get(k) is not None for k in PER_KWH_CHARGES):
            # What is left of the bill after these (fuel adjustment, tax, levies) is worked out by the page
            cycle["parts"] = {name: round(kwh * rates[key], 2) for key, name in PER_KWH_CHARGES.items()}
            cycle["parts"]["customer"] = rates.get("CustomerCharge") or 0.0
        months[iso(end)] = cycle
    return months


def load_history() -> dict:
    # A corrupt file raises here on purpose: starting fresh would overwrite the history
    try:
        return json.loads(HISTORY_FILE.read_text())
    except FileNotFoundError:
        return {"accounts": {}}


def save_history(history: dict) -> None:
    # Write to a temp file first so the web page never reads a half-written file
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=1))
    tmp.replace(HISTORY_FILE)


def backup_daily() -> None:
    """Keep one dated copy per day, so a bad write can't wipe the history."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for source in (HISTORY_FILE, NOTES_FILE):
        today = BACKUP_DIR / f"{source.stem}-{datetime.now(timezone.utc):%Y-%m-%d}.json"
        if today.exists() or not source.exists():
            continue
        shutil.copy2(source, today)
        for old in sorted(BACKUP_DIR.glob(f"{source.stem}-*.json"))[:-BACKUP_KEEP]:
            old.unlink()
        print(f"backup saved: {today.name}", flush=True)


def merge_months(saved: dict[str, dict], fetched: dict[str, dict]) -> dict[str, dict]:
    """The open cycle's end date can shift, so the old unbilled entry is dropped before the merge."""
    return {end: m for end, m in saved.items() if not m["unbilled"]} | fetched


def merge_bills(months: dict[str, dict], bills: list[dict]) -> None:
    """bills come from `mytnb bill-history`: [{'date': 'YYYY-MM-DD', 'amount': 'RM 548.40', ...}]."""
    for bill in bills:
        cycle = months.setdefault(bill["date"], {"kwh": None, "start": None, "unbilled": False})
        cycle["rm"] = num(bill["amount"])


def update_account(history: dict, account: str) -> None:
    usage = mytnb("usage", account)
    new_days = parse_days(usage)
    saved = history["accounts"].setdefault(account, {"name": "", "days": {}})
    saved["days"].update(new_days)
    saved["months"] = merge_months(saved.get("months", {}), parse_months(usage))
    try:
        merge_bills(saved["months"], mytnb("bill-history", account))
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as err:
        print(f"bill history skipped: {err!r}", flush=True)
    saved["summary"] = {
        "current_kwh": metric(usage.get("usage_metrics", []), "CURRENTUSAGE"),
        "current_rm": metric(usage.get("cost_metrics", []), "CURRENTCOST"),
        "projected_rm": metric(usage.get("cost_metrics", []), "PROJECTEDCOST"),
        "cycle_start": usage.get("current_cycle_start_date"),
    }
    saved["updated"] = datetime.now(timezone.utc).isoformat()
    print(f"{account[-4:]:>4}: fetched {len(new_days)} days, {len(saved['days'])} saved in total", flush=True)


def update_once(accounts: list[str]) -> None:
    history = load_history()
    for account in accounts:
        # One failed account must not lose the days already fetched for the others
        try:
            update_account(history, account)
        except subprocess.CalledProcessError as err:
            print(f"{account[-4:]:>4}: mytnb failed: {err.stderr.strip()[-500:]}", flush=True)
        except Exception as err:
            print(f"{account[-4:]:>4}: update failed: {err!r}", flush=True)
    save_history(history)
    backup_daily()


def requested_since(started: float) -> bool:
    try:
        return FETCH_REQUEST.stat().st_mtime > started
    except FileNotFoundError:
        return False


def wait_for_next_run(started: float) -> None:
    """Sleep until the interval is over, or until the page asks for a fetch."""
    while time.time() - started < INTERVAL_SECONDS and not requested_since(started):
        time.sleep(2)


if __name__ == "__main__":
    accounts = [a.strip() for a in os.environ.get("MYTNB_ACCOUNT", "").split(",") if a.strip()]
    if not accounts:
        raise SystemExit("MYTNB_ACCOUNT is empty: set at least one TNB account number in .env")
    while True:
        started = time.time()
        try:
            update_once(accounts)
        except Exception as err:  # keep the loop alive, try again next interval
            print(f"update failed: {err!r}", flush=True)
        wait_for_next_run(started)
