"""News fetchers. Each returns normalized items; the evidence label comes from config, not AI.

We keep only headline, link, date, source and (transiently, for classification) the short
feed description. Article text and abstracts are never fetched or stored.
"""
from __future__ import annotations

import email.utils
import hashlib
import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from .. import config
from . import http

log = logging.getLogger(__name__)


def item_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().rstrip("/").encode()).hexdigest()[:24]


def _strip_tags(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def make_item(source: str, url: str, title: str, published: str, description: str = "", **extra) -> dict:
    meta = config.NEWS_SOURCES[source]
    url = url.replace("http://www.fda.gov", "https://www.fda.gov")
    return {
        "id": item_id(url),
        "url": url,
        "title": _strip_tags(title)[:300],
        "date": published,
        "source": source,
        "source_name": meta["name"],
        "label": meta["label"],
        "description": _strip_tags(description)[:1500],
        **extra,
    }


def _rss_date(text: str | None) -> str:
    if not text:
        return date.today().isoformat()
    try:
        return email.utils.parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return text[:10]


def fetch_rss(source: str, url: str, limit: int = 25) -> list[dict]:
    status, body = http.get(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    root = ET.fromstring(body)
    items = []
    for node in root.iter("item"):
        link = (node.findtext("link") or "").strip()
        if not link:
            continue
        items.append(make_item(source, link, node.findtext("title") or "", _rss_date(node.findtext("pubDate")),
                               node.findtext("description") or ""))
        if len(items) >= limit:
            break
    return items


def fetch_fda_press() -> list[dict]:
    return fetch_rss("fda_press", "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml")


def _ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and len(s) == 8 else s


def fetch_openfda_drugs(days: int = 30, limit: int = 25) -> list[dict]:
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    q = (f"submissions.submission_status_date:[{start}+TO+{end}]"
         "+AND+submissions.submission_type:ORIG+AND+submissions.submission_status:AP")
    data = http.get_json(f"https://api.fda.gov/drug/drugsfda.json?search={q}&limit={limit}")
    items = []
    for r in data.get("results", []):
        appl = r.get("application_number", "")
        orig = next((s for s in r.get("submissions", []) if s.get("submission_type") == "ORIG"), {})
        brands = sorted({p.get("brand_name", "").title() for p in r.get("products", []) if p.get("brand_name")})
        forms = sorted({p.get("dosage_form", "").lower() for p in r.get("products", []) if p.get("dosage_form")})
        sponsor = (r.get("sponsor_name") or "").title()
        kind = "new drug application" if appl.startswith("NDA") else "generic drug application" if appl.startswith("ANDA") else "biologic application"
        title = f"FDA approves {', '.join(brands) or appl} ({sponsor})"
        url = ("https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo="
               + re.sub(r"\D", "", appl))
        hint = f"FDA approved a {kind} from {sponsor}" + (f" for a {forms[0]} product." if forms else ".")
        items.append(make_item("openfda_drugs", url, title, _ymd(orig.get("submission_status_date", "")),
                               f"{kind} {', '.join(forms)} {' '.join(r.get('openfda', {}).get('pharm_class_epc', []))}",
                               summary_hint=hint, company=sponsor))
    return items


def fetch_openfda_devices(limit: int = 15) -> list[dict]:
    items = []
    for search, kind in (("decision_code:DENG", "De Novo"), ("decision_code:SESE", "510(k)")):
        data = http.get_json(f"https://api.fda.gov/device/510k.json?search={search}&sort=decision_date:desc&limit={limit}")
        for r in data.get("results", []):
            k = r.get("k_number", "")
            name = (r.get("device_name") or "").strip().rstrip(".")
            applicant = (r.get("applicant") or "").title()
            url = (f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/denovo.cfm?ID={k}" if k.startswith("DEN")
                   else f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={k}")
            spec = r.get("openfda", {}).get("medical_specialty_description", "")
            items.append(make_item(
                "openfda_devices", url, f"FDA {kind} clearance: {name[:150]} ({applicant})", _ymd(r.get("decision_date", "")),
                f"{name} {spec} {r.get('openfda', {}).get('device_name', '')}",
                summary_hint=f"FDA cleared this {spec.lower() + ' ' if spec else ''}device from {applicant} through the {kind} pathway.",
                company=applicant))
    return items


def fetch_medrxiv(days: int = 2, limit: int = 40) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    data = http.get_json(f"https://api.biorxiv.org/details/medrxiv/{start}/{end}/0")
    seen, items = set(), []
    for r in data.get("collection", []):
        doi = r.get("doi")
        if not doi or doi in seen:
            continue
        seen.add(doi)
        items.append(make_item(
            "medrxiv", f"https://www.medrxiv.org/content/{doi}", r.get("title", ""), r.get("date", ""),
            r.get("category", ""), category=r.get("category"), license=r.get("license"),
            summary_hint=f"A preprint in {r.get('category', 'medicine')} posted to medRxiv. It has not been peer reviewed yet."))
        if len(items) >= limit:
            break
    return items


_pubmed_rate = http.RateLimiter(per_second=2.5)


def fetch_pubmed(days: int = 3, limit: int = 30) -> list[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    common = f"tool={config.APP_NAME}&email={urllib.parse.quote(config.CONTACT_EMAIL)}"
    _pubmed_rate.wait()
    ids = http.get_json(f"{base}/esearch.fcgi?db=pubmed&term={urllib.parse.quote(config.PUBMED_TERM)}"
                        f"&reldate={days}&datetype=edat&retmax={limit}&retmode=json&{common}")["esearchresult"]["idlist"]
    if not ids:
        return []
    _pubmed_rate.wait()
    summ = http.get_json(f"{base}/esummary.fcgi?db=pubmed&id={','.join(ids)}&retmode=json&{common}")["result"]
    items = []
    for pmid in ids:
        r = summ.get(pmid, {})
        pmc = next((a["value"] for a in r.get("articleids", []) if a.get("idtype") == "pmc"), None)
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/" if pmc else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        pubtypes = [t for t in r.get("pubtype", []) if t != "Journal Article"]
        journal = r.get("fulljournalname") or r.get("source", "")
        # Use the date PubMed indexed the record; journal issue dates can be months ahead.
        entrez = next((h.get("date") for h in r.get("history", []) if h.get("pubstatus") == "entrez"), "")
        sortdate = min((entrez or r.get("sortpubdate") or "")[:10].replace("/", "-"), date.today().isoformat())
        kind = pubtypes[0].lower() if pubtypes else "study"
        items.append(make_item(
            "pubmed", url, r.get("title", ""), sortdate or date.today().isoformat(),
            f"{journal} {' '.join(pubtypes)}", journal=journal, pmid=pmid,
            summary_hint=f"A {kind} published in {journal}."))
    return items


ATOM = "{http://www.w3.org/2005/Atom}"


def fetch_atom(source: str, url: str, limit: int = 20) -> list[dict]:
    status, body = http.get(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    items = []
    for entry in ET.fromstring(body).iter(f"{ATOM}entry"):
        link = next((l.get("href") for l in entry.findall(f"{ATOM}link") if l.get("rel", "alternate") == "alternate"), None)
        if not link:
            continue
        items.append(make_item(source, link, entry.findtext(f"{ATOM}title") or "",
                               (entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated") or "")[:10],
                               entry.findtext(f"{ATOM}summary") or ""))
        if len(items) >= limit:
            break
    return items


def fetch_cms_newsroom(limit: int = 20) -> list[dict]:
    """CMS packs an HTML anchor into <link> and leaves <title> empty; unpack both."""
    meta = config.NEWS_SOURCES["cms_newsroom"]
    status, body = http.get(meta["feed"])
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {meta['feed']}")
    items = []
    for node in ET.fromstring(body).iter("item"):
        raw = urllib.parse.unquote(node.findtext("link") or "")
        m = re.search(r'href="([^"]+)"[^>]*>(.*?)(</a>|$)', raw)
        if not m:
            continue
        url = urllib.parse.urljoin("https://www.cms.gov/", m.group(1))
        title = node.findtext("title") or m.group(2)
        try:
            published = datetime.strptime((node.findtext("pubDate") or "")[:15].strip(), "%a, %m/%d/%Y").date().isoformat()
        except ValueError:
            published = date.today().isoformat()
        items.append(make_item("cms_newsroom", url, title, published, node.findtext("description") or ""))
        if len(items) >= limit:
            break
    return items


def fetch_cdc_newsroom(limit: int = 15) -> list[dict]:
    """CDC's feed links go through a download redirect; resolve each to its cdc.gov page."""
    items = fetch_rss("cdc_newsroom", config.NEWS_SOURCES["cdc_newsroom"]["feed"], limit=limit)
    for item in items:
        final = http.resolve_redirect(item["url"])
        if final and final.startswith("https://www.cdc.gov/"):
            item.update(url=final, id=item_id(final))
    return items


def fetch_commercial(source: str) -> list[dict]:
    return fetch_rss(source, config.NEWS_SOURCES[source]["feed"], limit=20)


# ---------- free-to-read check for commercial links ----------

JSONLD_FREE_FALSE = re.compile(r'"isAccessibleForFree"\s*:\s*"?(false|False)"?')
PAYWALL_HINTS = re.compile(r"(subscribe to continue|subscribers only|paywall|metered-content|piano-offer)", re.I)


def free_to_read(url: str) -> tuple[bool, str]:
    """Metadata-only check: robots.txt, HTTP status, JSON-LD isAccessibleForFree, obvious walls.

    Reads at most the first 150 KB of HTML to find markup flags; no article text is kept.
    """
    if not http.robots_allowed(url):
        return False, "robots.txt disallows"
    status, head = http.get(url, timeout=15, max_bytes=150_000, headers={"Accept-Encoding": "identity"})
    if status in (401, 402, 403):
        return False, f"HTTP {status}"
    if status != 200:
        return False, f"HTTP {status}"
    text = head.decode("utf-8", "replace")
    if JSONLD_FREE_FALSE.search(text):
        return False, "isAccessibleForFree=false"
    if PAYWALL_HINTS.search(text):
        return False, "subscribe wall marker"
    return True, "ok"


FETCHERS = {
    "fda_press": fetch_fda_press,
    "openfda_drugs": fetch_openfda_drugs,
    "openfda_devices": fetch_openfda_devices,
    "medrxiv": fetch_medrxiv,
    "pubmed": fetch_pubmed,
    "the_conversation": lambda: fetch_atom("the_conversation", config.NEWS_SOURCES["the_conversation"]["feed"]),
    "cms_newsroom": fetch_cms_newsroom,
    "cdc_newsroom": fetch_cdc_newsroom,
    **{k: (lambda k=k: fetch_commercial(k)) for k, v in config.NEWS_SOURCES.items() if v.get("commercial")},
}
FETCHERS = {k: fn for k, fn in FETCHERS.items() if config.NEWS_SOURCES[k].get("enabled", True)}


def fetch_all() -> tuple[list[dict], dict]:
    """Run every fetcher; a failing source is logged and skipped, never fatal."""
    items, report = [], {}
    for name, fn in FETCHERS.items():
        try:
            got = fn()
            items.extend(got)
            report[name] = len(got)
        except Exception as err:  # noqa: BLE001
            log.warning("source %s failed: %s", name, err)
            report[name] = f"error: {err}"[:200]
    return items, report
