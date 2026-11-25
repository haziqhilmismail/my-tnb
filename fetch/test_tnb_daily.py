"""Run with: python test_tnb_daily.py"""

from tnb_daily import merge_bills, merge_months, parse_days, parse_months

usage = {
    "by_day": [{"days": [
        {"year": "2026", "month": "Sep", "day": "6", "consumption": "20.0 kWh", "amount": "RM 5.41"},
        {"year": "2026", "month": "9", "day": "7", "consumption": "18", "amount": "4.80", "is_estimated_reading": True},
        {"year": "2026", "month": "Sep", "day": "8", "is_missing_reading": True},
        {"year": "2026", "month": "Sep", "day": "9"},
    ]}],
    "by_month": {"months": [
        {"billing_start_date": "20260823", "billing_end_date": "20260922", "usage_total": "1000", "amount_total": "548.40"},
        {"billing_start_date": "20260923", "billing_end_date": "20261022", "usage_total": "334", "amount_total": "78.26",
         "is_unbilled": True},
    ]},
    "tariff_blocks_legend_rp4": [
        {"items": [{"block_id": "EnergyCharge", "block_price": "0.2703"}, {"block_id": "CapacityCharge", "block_price": "0.0455"},
                   {"block_id": "NetworkCharge", "block_price": "0.1285"}, {"block_id": "CustomerCharge", "block_price": "10.00"}]},
        {"items": []},
    ],
}

assert parse_days(usage) == {
    "2026-09-06": {"kwh": 20.0, "rm": 5.41, "est": False},
    "2026-09-07": {"kwh": 18.0, "rm": 4.8, "est": True},
}, parse_days(usage)

months = parse_months(usage)
assert months == {
    "2026-09-22": {"rm": 548.4, "kwh": 1000.0, "start": "2026-08-23", "unbilled": False,
                   "parts": {"energy": 270.3, "capacity": 45.5, "network": 128.5, "customer": 10.0}},
    "2026-10-22": {"rm": 78.26, "kwh": 334.0, "start": "2026-09-23", "unbilled": True},
}, months

# rate tables that do not line up with the months are ignored, so no bill gets the wrong split
shifted = usage | {"tariff_blocks_legend_rp4": usage["tariff_blocks_legend_rp4"][:1]}
assert all("parts" not in m for m in parse_months(shifted).values())

# the open cycle's end date moved from 21 Oct to 22 Oct: the stale unbilled entry goes, billed ones stay
saved = {"2026-08-22": {"rm": 500.0, "unbilled": False}, "2026-10-21": {"rm": 70.0, "unbilled": True}}
assert sorted(merge_months(saved, months)) == ["2026-08-22", "2026-09-22", "2026-10-22"]

# old bills only from bill-history: amount only; a known cycle keeps its kWh and gets the billed amount
merged = {"2026-09-22": {"rm": 1.0, "kwh": 1000.0, "start": "2026-08-23", "unbilled": False}}
merge_bills(merged, [{"date": "2026-07-22", "amount": "RM 410.00"}, {"date": "2026-09-22", "amount": "548.40"}])
assert merged == {
    "2026-09-22": {"rm": 548.4, "kwh": 1000.0, "start": "2026-08-23", "unbilled": False},
    "2026-07-22": {"rm": 410.0, "kwh": None, "start": None, "unbilled": False},
}, merged

print("ok")
