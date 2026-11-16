"""Public health companies raising money, from the press releases they file with the SEC (Form 8-K).

When a listed biotech, pharma, device or care company prices or closes a stock offering or a private
placement, it files the press release as an 8-K exhibit the same day or the next. That makes these
the freshest funding records we can use: SEC filings are public, free to read, and EDGAR allows
automated access within its fair-access rules (identifying User-Agent, at most 10 requests a second).

Only facts the filing states go in: the headline, the amount (from the headline, else "gross
proceeds"), the date and the company. A filing counts only if its headline announces an offering,
placement or financing, so earnings releases that mention past raises are left out.
"""
from __future__ import annotations

import html
import logging
import re
import urllib.parse
from datetime import date, timedelta

from .. import classify
from . import http
from .funding import SEC_HEADERS, _sec_rate

log = logging.getLogger(__name__)

KIND = "SEC 8-K press release"

# Standard Industrial Classification codes for health companies -> our Sector.
SIC_SECTORS = [
    (r"^283[346]$", "Life Sciences and Biotech"),  # medicinal chemicals, drugs, biologics
    (r"^2835$", "Med Tech"),                        # in vitro diagnostics
    (r"^(384[1-5]|3851|5047)$", "Med Tech"),         # instruments, devices, X-ray, dental, optical, wholesale
    (r"^8731$", "Life Sciences and Biotech"),       # commercial biological research
    (r"^(80\d\d|6324)$", "Care Delivery and Payers"),  # health services, hospital and medical plans
]

# Phrases that appear in offering press releases. EDGAR full-text search takes one phrase set per query.
QUERIES = [
    '"announces pricing" "gross proceeds"',
    '"announces closing" "gross proceeds"',
    '"private placement" "gross proceeds"',
    '"registered direct offering" "gross proceeds"',
    '"initial public offering" "gross proceeds"',
]

HEADLINE = re.compile(r"\b(announces?|prices?|priced|closes?|closed|completes?|completed|raises?|secures?)\b"
                      r".*\b(offering|placement|financing|private investment|PIPE)\b", re.I)
EARNINGS = re.compile(r"\b(quarter|fiscal|results|earnings)\b", re.I)
MONEY = r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion|[mb]n?)?\b"
HEADLINE_AMOUNT = re.compile(MONEY, re.I)
PROCEEDS_AMOUNT = re.compile(r"gross proceeds[^.$]{0,80}?" + MONEY, re.I)
TICKER = re.compile(r"\s*\(([A-Z.]{1,6})(?:,[^)]*)?\)\s*")


def sector_for(sics: list[str], headline: str) -> str | None:
    for code in sics:
        for rx, sector in SIC_SECTORS:
            if re.match(rx, code):
                # The headline can be more specific than the industry code (an AI company filing as 3841).
                return classify.sector_from_text(headline, sector) if sector == "Life Sciences and Biotech" else sector
    return None


def _amount(m: re.Match | None) -> float | None:
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    n *= 1e9 if unit.startswith("b") else 1e6 if unit.startswith("m") else 1
    return n if n >= 1e5 else None  # "$1.00 per share" is a price, not a raise


def stage_for(headline: str) -> str | None:
    if re.search(r"initial public offering|\bIPO\b", headline, re.I):
        return "IPO"
    if re.search(r"public offering|registered direct|underwritten", headline, re.I):
        return "Public offering"
    if re.search(r"private placement|private investment|\bPIPE\b", headline, re.I):
        return "Private placement"
    if re.search(r"\boffering\b", headline, re.I):
        return "Public offering"
    return None  # "financing" alone doesn't say which kind


def plain_text(body: bytes) -> str:
    t = body.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    lines = (re.sub(r"[ \t\xa0]+", " ", x).strip() for x in t.splitlines())
    return "\n".join(x for x in lines if x)


BOILERPLATE = re.compile(r"^(for immediate release|press release|news release|release|document|edgarfiling|(edgarfiling\s+)?exhibit\b.*"
                         r"|ex-99.*|\S+\.htm|[\d.]+|on \w+day,.*)$", re.I)
LEADING_JUNK = re.compile(r"^\W*(edgarfiling\s+)?(exhibit\s*)?(99\.\d+\s+)?", re.I)
SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def is_title_wrap(line: str) -> bool:
    """A headline's next line, such as "Million Financing": short and in Title Case. A dateline
    fragment ("SAN", "RUTHERFORD,", "$4") is not one."""
    words = line.split()
    if len(words) < 2 or line.endswith(",") or line.isupper():
        return False
    return len(line) <= 90 and not re.search(r"\b20\d\d\b", line) and all(
        w[0].isupper() or w[0] in "$0123456789(" or w.lower() in SMALL_WORDS for w in words)


def find_headline(text: str) -> str | None:
    """The release's own headline: the first real line after the "Exhibit 99" marker, joined with the
    lines it wraps onto (a company name alone on a line, or a Title Case continuation). Bullets and
    body text further down never count."""
    lines = text.splitlines()
    start = next((i + 1 for i, x in enumerate(lines[:40]) if re.match(r"^exhibit\s*99", x, re.I)), 0)
    body = [x for x in lines[start:start + 12] if not BOILERPLATE.match(x)]
    if not body:
        return None
    head = LEADING_JUNK.sub("", body[0])
    for nxt in body[1:4]:
        if re.search(r"[.!?]$", head) or re.search(r"\b20\d\d\b", nxt) or len(head) + len(nxt) > 300:
            break
        if len(head.split()) <= 3 or is_title_wrap(nxt):
            head = f"{head} {nxt}"
        else:
            break
    head = head.strip()
    if 20 <= len(head) <= 300 and HEADLINE.search(head) and not EARNINGS.search(head):
        return head
    return None


def company_name(display_name: str) -> tuple[str, str | None]:
    """'PepGen Inc.  (PEPG)  (CIK 0001835597)' -> ('PepGen Inc.', 'PEPG')."""
    name = re.sub(r"\s*\(CIK \d+\)\s*$", "", display_name)
    m = TICKER.search(name)
    ticker = m.group(1) if m else None
    name = TICKER.sub(" ", name).strip()
    if name.isupper():
        name = name.title().replace("Llc", "LLC")
    return name.split("/")[0].strip(), ticker


def search(days: int = 10) -> list[dict]:
    """Health-company 8-K press-release exhibits matching any offering phrase, newest first, one per filing."""
    end, start = date.today(), date.today() - timedelta(days=days)
    found: dict[str, dict] = {}
    for q in QUERIES:
        _sec_rate.wait()
        try:
            data = http.get_json("https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(
                {"q": q, "forms": "8-K", "dateRange": "custom", "startdt": start, "enddt": end}), headers=SEC_HEADERS)
        except Exception as err:  # noqa: BLE001 - one failed phrase shouldn't drop the rest
            log.warning("8-K search %s: %s", q, err)
            continue
        for hit in data.get("hits", {}).get("hits", []):
            src = hit["_source"]
            adsh, _, doc = hit["_id"].partition(":")
            if not src.get("file_type", "").upper().startswith("EX-99") or "2.02" in (src.get("items") or []):
                continue  # press-release exhibits only; 2.02 = quarterly results
            if not any(re.match(rx, s) for s in src.get("sics") or [] for rx, _ in SIC_SECTORS):
                continue
            found.setdefault(adsh, {"adsh": adsh, "doc": doc, "cik": src["ciks"][0], "file_date": src.get("file_date"),
                                    "display_name": (src.get("display_names") or [""])[0], "sics": src.get("sics") or [],
                                    "location": (src.get("biz_locations") or [""])[0]})
    return sorted(found.values(), key=lambda f: f["file_date"] or "", reverse=True)


def doc_url(f: dict) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(f['cik'])}/{f['adsh'].replace('-', '')}/{f['doc']}"


def to_record(f: dict, text: str) -> dict | None:
    headline = find_headline(text)
    if not headline:
        return None
    sector = sector_for(f["sics"], headline)
    if not sector:
        return None
    company, ticker = company_name(f["display_name"])
    amount = _amount(HEADLINE_AMOUNT.search(headline)) or _amount(PROCEEDS_AMOUNT.search(text))
    focus = [a for a, rx in classify.FOCUS_KEYWORDS if re.search(rx, text[:1500], re.I)][:3]
    return {
        "id": f"sec8k#{f['adsh']}",
        "company": company,
        "ticker": ticker,
        "headline": headline,
        "amount_usd": amount,
        "round_stage": stage_for(headline),
        "date": f["file_date"],
        "investors": [],
        "source_url": doc_url(f),
        "source_name": "SEC 8-K filing",
        "source_kind": KIND,
        "state": f.get("location"),
        "sector": sector,
        "focus_areas": focus,
    }


def same_raise(a: dict, b: dict) -> bool:
    """A pricing release and its closing release a few days later describe one raise."""
    if a["company"] != b["company"] or a.get("round_stage") != b.get("round_stage"):
        return False
    gap = abs(date.fromisoformat(a["date"]) - date.fromisoformat(b["date"]))
    return gap <= timedelta(days=10)


def fetch_new(existing: list[dict], limit: int = 100) -> list[dict]:
    """New offering records. `existing` is the stored 8-K rows, used to skip seen filings and repeat raises."""
    seen_ids = {r["id"] for r in existing}
    kept = [r for r in existing if r.get("source_kind") == KIND]
    records: list[dict] = []
    for f in search(days=10 if kept else 90):  # first run back-fills the default 90-day view
        if f"sec8k#{f['adsh']}" in seen_ids or len(records) >= limit:
            continue
        _sec_rate.wait()
        status, body = http.get(doc_url(f), headers=SEC_HEADERS)
        if status != 200:
            log.warning("8-K %s: HTTP %s", f["adsh"], status)
            continue
        rec = to_record(f, plain_text(body))
        if rec and not any(same_raise(rec, r) for r in kept + records):
            records.append(rec)
    return records
