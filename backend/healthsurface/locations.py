"""Derive countries from free-text job locations ("Boston, MA", "Remote - USA", "Pune, India").

Job boards write locations however they like, so search for "United States" would otherwise
miss "New York, NY". Pure Python, no AWS code.
"""
from __future__ import annotations

import re

US = "United States"

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# Order matters only for readability; every pattern is checked.
COUNTRY_PATTERNS: list[tuple[str, str]] = [
    (US, r"\bunited states\b|\bu\.?s\.?a?\b|\bamerica\b|\bwashington,? d\.?c\.?"),
    (US, r"\b(" + "|".join(name.lower() for name in US_STATES.values()) + r")\b"),
    (US, r"\b(san francisco|sf|ny|bay area|silicon valley|nyc|ny office|new york|boston|chicago|chi office"
         r"|miami|palo alto|redwood city|mountain view|cincinnati|durham office|greater orlando|lsnyc)\b"),
    ("Canada", r"\bcanada\b|\btoronto\b|\bvancouver\b|\bmontreal\b"),
    ("United Kingdom", r"\bunited kingdom\b|\buk\b|\blondon\b|\bengland\b|\bscotland\b"),
    ("India", r"\bindia\b|\bpune\b|\bmumbai\b|\bbengaluru\b|\bbangalore\b|\bchennai\b|\bbhubaneswar\b|\bhinganghat\b|\bpatiala\b"),
    ("Germany", r"\bgermany\b|\bberlin\b|\bmunich\b"),
    ("Portugal", r"\bportugal\b|\blisbon\b|\bporto\b"),
    ("France", r"\bfrance\b|\bparis\b"),
    ("Italy", r"\bitaly\b|\bmilan\b"),
    ("Japan", r"\bjapan\b|\btokyo\b|東京|千葉"),
    ("Brazil", r"\bbrazil\b|\bsao paulo\b|\brio de janeiro\b"),
    ("Mexico", r"\bmexico\b"),
    ("Finland", r"\bfinland\b|\bhelsinki\b"),
    ("Ireland", r"\bireland\b|\blimerick\b|\bdublin\b"),
    ("Israel", r"\bisrael\b|\btel aviv\b"),
    ("Singapore", r"\bsingapore\b"),
    ("Philippines", r"\bphilippines\b"),
    ("South Africa", r"\bsouth africa\b"),
    ("South Korea", r"\bsouth korea\b|\bseoul\b"),
    ("Greece", r"\bgreece\b"),
    ("Hungary", r"\bhungary\b|\bbudapest\b"),
    ("Australia", r"\baustralia\b|\balice springs\b|\bsydney\b|\bmelbourne\b"),
    ("New Zealand", r"\bnew zealand\b"),
    ("Malaysia", r"\bmalaysia\b"),
    ("Pakistan", r"\bpakistan\b"),
    ("Bangladesh", r"\bbangladesh\b"),
    ("Sri Lanka", r"\bsri lanka\b|\bcolombo\b"),
    ("Europe", r"\beurope\b"),
]
_COMPILED = [(country, re.compile(rx, re.I)) for country, rx in COUNTRY_PATTERNS]
# "Boston, MA" / "Remote - CA" / "Austin, TX (Remote)": a state code after a comma or dash.
_STATE_CODE = re.compile(r"(?:,|-)\s*(" + "|".join(US_STATES) + r")\b(?!\w)")


def countries_for(location: str | None) -> list[str]:
    """All countries a location string mentions, United States first. Empty when unknown (e.g. "Remote")."""
    text = location or ""
    found = [country for country, rx in _COMPILED if rx.search(text)]
    if _STATE_CODE.search(text):
        found.append(US)
    found = list(dict.fromkeys(found))
    # "Georgia" alone is a US state here (US employers); "New Mexico" must not also mean Mexico.
    if "Mexico" in found and re.search(r"\bnew mexico\b", text, re.I) and not re.search(r"(?<!new )\bmexico\b", text, re.I):
        found.remove("Mexico")
    return sorted(found, key=lambda c: (c != US, c))
