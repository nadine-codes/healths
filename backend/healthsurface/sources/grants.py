"""NIH RePORTER: small business research grants (SBIR and STTR) to health companies.

US government data (public domain). Each award becomes a funding record with round stage
"Grant", the awarded amount and the notice date, linked to its RePORTER project page.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date, timedelta

from .. import classify, config

# SBIR (R43, R44, U43, U44, SB1) and STTR (R41, R42) small business activity codes.
ACTIVITY_CODES = ["R41", "R42", "R43", "R44", "U43", "U44", "SB1"]
FIELDS = ["ProjectTitle", "Organization", "AwardAmount", "AwardNoticeDate", "ApplId", "ActivityCode", "AgencyIcAdmin"]


def _search(days: int, limit: int) -> list[dict]:
    body = json.dumps({
        "criteria": {"award_notice_date": {"from_date": str(date.today() - timedelta(days=days)), "to_date": str(date.today())},
                     "activity_codes": ACTIVITY_CODES},
        "include_fields": FIELDS, "limit": limit, "sort_field": "award_notice_date", "sort_order": "desc",
    }).encode()
    req = urllib.request.Request("https://api.reporter.nih.gov/v2/projects/search", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("results", [])


def to_record(r: dict) -> dict | None:
    org = (r.get("organization") or {}).get("org_name")
    if not org or not r.get("appl_id"):
        return None
    title = r.get("project_title") or ""
    focus = [f for f, rx in classify.FOCUS_KEYWORDS if re.search(rx, title, re.I)][:3]
    program = "STTR" if r.get("activity_code") in ("R41", "R42") else "SBIR"
    institute = (r.get("agency_ic_admin") or {}).get("abbreviation", "NIH")
    return {
        "id": f"nih#{r['appl_id']}",
        "company": " ".join(org.split()).title().replace("Llc", "LLC"),
        "amount_usd": r.get("award_amount") or None,
        "round_stage": "Grant",
        "date": (r.get("award_notice_date") or "")[:10],
        "investors": [f"NIH {institute}"],
        "source_url": f"https://reporter.nih.gov/project-details/{r['appl_id']}",
        "source_name": "NIH RePORTER",
        "source_kind": f"NIH {program} grant",
        "project_title": title[:200],
        "sector": "Life Sciences and Biotech",
        "focus_areas": focus,
    }


def fetch_new(existing_ids: set[str], days: int = 45, limit: int = 100) -> list[dict]:
    records = [to_record(r) for r in _search(days, limit)]
    return [r for r in records if r and r["id"] not in existing_ids]
