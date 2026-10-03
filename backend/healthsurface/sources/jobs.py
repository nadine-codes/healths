"""Jobs from verified Greenhouse, Lever and Ashby boards, plus the RemoteOK public feed.

Only boards listed in companies.json (verified by scripts/verify_boards.py) or verified at run
time for funded companies are used. We never scrape job boards or invent listings.
"""
from __future__ import annotations

import html
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import http

log = logging.getLogger(__name__)

COMPANIES: list[dict] = json.loads((Path(__file__).resolve().parent.parent / "companies.json").read_text())
PER_COMPANY_LIMIT = 60
REMOTE_RE = re.compile(r"\bremote\b|anywhere|work from home", re.I)

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
}


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):  # Lever uses epoch milliseconds
        return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    return str(value)[:10]


def _job(company: dict, provider: str, raw_id, title, url, location, posted, commitment="", text="", remote=None) -> dict:
    location = (location or "").strip()
    return {
        "id": f"{provider}#{company['token']}#{raw_id}",
        "company": company["name"],
        "title": html.unescape(title or "").strip(),
        "url": url,
        "location": location,
        "remote": bool(remote) if remote is not None else bool(REMOTE_RE.search(f"{location} {title}")),
        "posted": _iso(posted),
        "commitment": commitment or "",
        "text": text[:800],
        "source": provider,
        "source_name": {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby"}[provider] + f" board ({company['name']})",
        "sector": company.get("sector"),
        "focus_areas": company.get("focus_areas", []),
    }


# jobs.lever.co and api.lever.co robots.txt ask for a 1 second crawl delay.
_lever_rate = http.RateLimiter(per_second=1)


def fetch_board(company: dict) -> list[dict]:
    provider, token = company["provider"], company["token"]
    if provider == "lever":
        _lever_rate.wait()
    data = http.get_json(ENDPOINTS[provider].format(t=token), timeout=25)
    jobs = []
    if provider == "greenhouse":
        for j in data.get("jobs", []):
            jobs.append(_job(company, provider, j["id"], j.get("title"), j.get("absolute_url"),
                             (j.get("location") or {}).get("name"), j.get("first_published") or j.get("updated_at")))
    elif provider == "lever":
        for j in data:
            cats = j.get("categories") or {}
            jobs.append(_job(company, provider, j["id"], j.get("text"), j.get("hostedUrl"), cats.get("location"),
                             j.get("createdAt"), cats.get("commitment", ""), j.get("descriptionPlain", "")[:800],
                             remote=(j.get("workplaceType") == "remote") or None))
    else:
        for j in data.get("jobs", []):
            if not j.get("isListed", True):
                continue
            jobs.append(_job(company, provider, j["id"], j.get("title"), j.get("jobUrl"), j.get("location"),
                             j.get("publishedAt"), j.get("employmentType", ""), j.get("descriptionPlain", "")[:800],
                             remote=j.get("isRemote")))
    jobs.sort(key=lambda j: j["posted"] or "", reverse=True)
    return jobs[:PER_COMPANY_LIMIT]


HEALTH_RE = re.compile(r"health|medical|clinic|biotech|pharma|patient|care\b|hospital|nurse|therap|wellness|telehealth", re.I)


def fetch_remoteok(limit: int = 60) -> list[dict]:
    """Remote OK public API. Their terms require crediting Remote OK and linking to the posting on remoteok.com."""
    data = http.get_json("https://remoteok.com/api", timeout=25)
    jobs = []
    for j in data[1:]:  # first element is the legal notice
        blob = f"{j.get('company', '')} {j.get('position', '')} {' '.join(j.get('tags') or [])}"
        if not HEALTH_RE.search(blob):
            continue
        company = {"name": html.unescape(j.get("company") or "Unknown"), "token": "remoteok"}
        job = _job(company, "greenhouse", j.get("id"), j.get("position"), j.get("url"), j.get("location") or "Remote",
                   j.get("date"), " ".join(j.get("tags") or []), remote=True)
        # Remote OK API terms: name "Remote OK" as the source and link (followed) to the job's remoteok.com URL.
        job.update(id=f"remoteok#{j.get('id')}", source="remoteok", source_name="Remote OK", sector=None, focus_areas=[])
        jobs.append(job)
        if len(jobs) >= limit:
            break
    return jobs


def _slug_tokens(name: str) -> list[str]:
    base = re.sub(r"[,.]|\b(inc|llc|corp|corporation|co|ltd|holdings|pbc)\b", " ", name.lower())
    words = [w for w in re.split(r"[^a-z0-9]+", base) if w]
    if not words:
        return []
    joined, dashed = "".join(words), "-".join(words)
    return [t for t in dict.fromkeys([joined, dashed]) if len(t) >= 6]


def verify_company(name: str, sector: str | None, focus: list[str]) -> dict | None:
    """Try to find and verify a board for a funded company. Greenhouse also confirms the board name."""
    for token in _slug_tokens(name):
        for provider, url in ENDPOINTS.items():
            status, body = http.get(url.format(t=token), timeout=10)
            if status != 200:
                continue
            try:
                data = json.loads(body)
            except ValueError:
                continue
            jobs = data.get("jobs") if isinstance(data, dict) else data
            if not jobs:
                continue
            if provider == "greenhouse":
                s2, meta = http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}", timeout=10)
                board = json.loads(meta).get("name", "") if s2 == 200 else ""
                if _slug_tokens(board)[:1] != _slug_tokens(name)[:1]:
                    continue
            return {"name": name, "sector": sector, "focus_areas": focus, "provider": provider, "token": token,
                    "jobs_at_verify": len(jobs), "added_from": "funding"}
    return None


def fetch_all(extra_companies: list[dict]) -> tuple[list[dict], dict, set[str]]:
    """Returns (jobs, report, boards_ok) where boards_ok are 'provider#token' prefixes that loaded."""
    companies = COMPANIES + extra_companies
    report, jobs, boards_ok = {}, [], set()

    def one(c):
        try:
            return c, fetch_board(c), None
        except Exception as err:  # noqa: BLE001
            return c, [], err

    with ThreadPoolExecutor(8) as pool:
        for c, got, err in pool.map(one, companies):
            if err:
                report[c["name"]] = f"error: {err}"[:120]
                continue
            boards_ok.add(f"{c['provider']}#{c['token']}#")
            jobs.extend(got)
            report[c["name"]] = len(got)
    try:
        rok = fetch_remoteok()
        jobs.extend(rok)
        boards_ok.add("remoteok#")
        report["RemoteOK"] = len(rok)
    except Exception as err:  # noqa: BLE001
        report["RemoteOK"] = f"error: {err}"[:120]
    return jobs, report, boards_ok
