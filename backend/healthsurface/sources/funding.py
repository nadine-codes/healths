"""SEC EDGAR Form D filings from health companies.

Form D shows the issuer, industry group, amount sold and first-sale date. It usually does not
name the round or investors, so those stay empty unless a news story states them.
SEC fair-access rules: at most 10 requests per second with an identifying User-Agent.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from .. import classify, config
from . import http

log = logging.getLogger(__name__)

# Form D industry group -> our Sector. Only these groups are pulled.
INDUSTRY_SECTORS = {
    "Biotechnology": "Life Sciences and Biotech",
    "Pharmaceuticals": "Pharma",
    "Other Health Care": "Health Tech",
    "Hospitals and Physicians": "Care Delivery and Payers",
    "Health Insurance": "Care Delivery and Payers",
}

_sec_rate = http.RateLimiter(per_second=8)
# SEC asks for "Company Name contact@email" with nothing else in the header.
SEC_HEADERS = {"User-Agent": f"{config.APP_NAME} {config.CONTACT_EMAIL}".strip()}


def search_filings(days: int = 14) -> list[dict]:
    end, start = date.today(), date.today() - timedelta(days=days)
    found = {}
    for group in INDUSTRY_SECTORS:
        q = urllib.parse.quote(f'"{group}"')
        _sec_rate.wait()
        data = http.get_json(f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=D&dateRange=custom"
                             f"&startdt={start}&enddt={end}", headers=SEC_HEADERS)
        for hit in data.get("hits", {}).get("hits", []):
            src = hit["_source"]
            if src.get("file_type") != "D":  # skip amendments (D/A)
                continue
            adsh, _, doc = hit["_id"].partition(":")
            found[adsh] = {"adsh": adsh, "doc": doc, "cik": src["ciks"][0], "file_date": src.get("file_date"),
                           "location": (src.get("biz_locations") or [""])[0]}
    return list(found.values())


def _text(root: ET.Element, tag: str) -> str:
    node = root.find(f".//{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def _money(value: str) -> float | None:
    try:
        n = float(value)
        return n if n > 0 else None
    except ValueError:
        return None


def parse_form_d(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    return {
        "company": _text(root, "entityName"),
        "industry": _text(root, "industryGroupType"),
        "amount_sold": _money(_text(root, "totalAmountSold")),
        "offering_amount": _money(_text(root, "totalOfferingAmount")),
        "first_sale": _text(root, "dateOfFirstSale/value") or None,
        "is_amendment": _text(root, "isAmendment") == "true",
    }


def filing_url(cik: str, adsh: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{adsh}-index.htm"


def to_record(filing: dict, form: dict) -> dict | None:
    sector = INDUSTRY_SECTORS.get(form["industry"])
    if not sector or form["is_amendment"] or not form["company"]:
        return None
    name = re.sub(r"\s+", " ", form["company"]).strip()
    focus = [f for f, rx in classify.FOCUS_KEYWORDS if re.search(rx, name, re.I)][:3]
    return {
        "id": f"formd#{filing['adsh']}",
        "company": name,
        "amount_usd": form["amount_sold"],
        "offering_amount_usd": form["offering_amount"],
        "round_stage": None,
        "date": filing["file_date"],
        "investors": [],
        "source_url": filing_url(filing["cik"], filing["adsh"]),
        "source_name": "SEC Form D filing",
        "source_kind": "SEC Form D",
        "industry": form["industry"],
        "state": filing.get("location"),
        "sector": sector,
        "focus_areas": focus,
    }


def fetch_new(existing_ids: set[str], limit: int = 120) -> list[dict]:
    records = []
    for filing in search_filings():
        if f"formd#{filing['adsh']}" in existing_ids or len(records) >= limit:
            continue
        _sec_rate.wait()
        url = f"https://www.sec.gov/Archives/edgar/data/{int(filing['cik'])}/{filing['adsh'].replace('-', '')}/{filing['doc']}"
        status, body = http.get(url, headers=SEC_HEADERS)
        if status != 200:
            log.warning("form D %s: HTTP %s", filing["adsh"], status)
            continue
        try:
            rec = to_record(filing, parse_form_d(body))
        except ET.ParseError:
            continue
        if rec:
            records.append(rec)
    return records
