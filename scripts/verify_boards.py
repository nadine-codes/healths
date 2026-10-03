"""Verify Greenhouse, Lever and Ashby board tokens for seed companies.

Tries each candidate token against each provider's public board endpoint and keeps only the
ones that return at least one job. Writes backend/healthsurface/companies.json.
Usage: python scripts/verify_boards.py
"""
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json&limit=500",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
}

# name, sector, focus areas, candidate tokens
SEED = [
    ("Hinge Health", "Health Tech", ["Pain and chronic conditions", "Fitness and recovery"], ["hingehealth"]),
    ("Omada Health", "Health Tech", ["Diabetes", "Metabolic health and obesity"], ["omadahealth"]),
    ("Oura", "Health Tech", ["Sleep", "Longevity and healthspan"], ["oura", "ouraring"]),
    ("Whoop", "Health Tech", ["Fitness and recovery", "Sleep"], ["whoop"]),
    ("Function Health", "Health Tech", ["Longevity and healthspan"], ["functionhealth", "function-health"]),
    ("Spring Health", "Health Tech", ["Mental health"], ["springhealth", "springhealth66"]),
    ("Lyra Health", "Health Tech", ["Mental health"], ["lyrahealth", "lyra-health"]),
    ("Headspace", "Health Tech", ["Mental health", "Sleep"], ["headspace", "hs"]),
    ("Maven Clinic", "Health Tech", ["Women's health", "Pediatrics and family health"], ["mavenclinic", "maven-clinic"]),
    ("Tempus", "Health AI", ["Cancer and oncology", "Genetics and precision medicine"], ["tempus", "tempuslabs"]),
    ("Flatiron Health", "Health Data and IT", ["Cancer and oncology"], ["flatironhealth"]),
    ("Abridge", "Health AI", ["Senior care"], ["abridge"]),
    ("Ambience Healthcare", "Health AI", [], ["ambiencehealthcare", "ambience"]),
    ("Included Health", "Care Delivery and Payers", ["Mental health"], ["includedhealth"]),
    ("Devoted Health", "Care Delivery and Payers", ["Senior care"], ["devoted", "devotedhealth"]),
    ("Oscar Health", "Care Delivery and Payers", [], ["oscar", "oscarhealth"]),
    ("Color Health", "Health Tech", ["Cancer and oncology", "Genetics and precision medicine"], ["color", "colorhealth"]),
    ("Noom", "Health Tech", ["Metabolic health and obesity", "Nutrition and gut health"], ["noom"]),
    ("Virta Health", "Health Tech", ["Diabetes", "Metabolic health and obesity"], ["virtahealth", "virta"]),
    ("Garner Health", "Care Delivery and Payers", [], ["garnerhealth", "garner"]),
    ("Commure", "Health Data and IT", [], ["commure"]),
    ("Freenome", "Life Sciences and Biotech", ["Cancer and oncology"], ["freenome"]),
    ("GRAIL", "Life Sciences and Biotech", ["Cancer and oncology"], ["grail", "grailbio"]),
    ("insitro", "Life Sciences and Biotech", ["Genetics and precision medicine"], ["insitro"]),
    ("Recursion", "Life Sciences and Biotech", [], ["recursionpharmaceuticals", "recursion"]),
    ("Zocdoc", "Health Tech", [], ["zocdoc"]),
    ("Cityblock Health", "Care Delivery and Payers", ["Senior care", "Mental health"], ["cityblockhealth", "cityblock"]),
    ("Carbon Health", "Care Delivery and Payers", [], ["carbonhealth"]),
    ("Sword Health", "Health Tech", ["Pain and chronic conditions", "Fitness and recovery"], ["swordhealth", "sword-health"]),
    ("Talkiatry", "Care Delivery and Payers", ["Mental health"], ["talkiatry"]),
    ("Thirty Madison", "Health Tech", ["Men's health", "Women's health"], ["thirtymadison"]),
    ("Levels", "Health Tech", ["Metabolic health and obesity"], []  # "levels" on Ashby is a different company),
    ("Eight Sleep", "Health Tech", ["Sleep"], ["eightsleep", "eight-sleep"]),
    ("Superpower", "Health Tech", ["Longevity and healthspan"], ["superpower"]),
    ("Midi Health", "Care Delivery and Payers", ["Women's health", "Hormones"], ["midihealth", "midi-health", "joinmidi"]),
    ("Nourish", "Care Delivery and Payers", ["Nutrition and gut health"], ["nourish", "usenourish"]),
    ("Ro", "Health Tech", ["Metabolic health and obesity", "Men's health"], ["ro", "roman"]),
    ("Hims & Hers", "Health Tech", ["Men's health", "Women's health"], ["hims", "himshers", "hims-and-hers"]),
    ("Elation Health", "Health Data and IT", [], ["elationhealth", "elation"]),
    ("Komodo Health", "Health Data and IT", [], ["komodohealth"]),
    ("Sprinter Health", "Care Delivery and Payers", ["Senior care"], ["sprinterhealth"]),
    ("Pomelo Care", "Care Delivery and Payers", ["Women's health", "Pediatrics and family health"], ["pomelocare"]),
    ("Equip Health", "Care Delivery and Payers", ["Mental health"], ["equip", "equiphealth"]),
    ("Charlie Health", "Care Delivery and Payers", ["Mental health"], ["charliehealth"]),
    ("Nabla", "Health AI", [], ["nabla"]),
    ("OpenEvidence", "Health AI", [], ["openevidence"]),
    ("Hippocratic AI", "Health AI", [], ["hippocraticai", "hippocratic-ai"]),
    ("Natera", "Life Sciences and Biotech", ["Genetics and precision medicine", "Women's health"], ["natera"]),
    ("Viz.ai", "Health AI", ["Neurology and brain health", "Cardiovascular"], ["vizai", "viz"]),
    ("Cleerly", "Health AI", ["Cardiovascular"], ["cleerly"]),
]


def count_jobs(provider: str, token: str) -> int:
    url = ENDPOINTS[provider].format(t=token)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "HealthSurface"}), timeout=15) as r:
            data = json.load(r)
    except Exception:
        return 0
    if provider == "greenhouse":
        return len(data.get("jobs", []))
    if provider == "lever":
        return len(data) if isinstance(data, list) else 0
    return len(data.get("jobs", []))


def verify(entry):
    name, sector, focus, tokens = entry
    for token in tokens:
        for provider in ENDPOINTS:
            n = count_jobs(provider, token)
            if n:
                return {"name": name, "sector": sector, "focus_areas": focus, "provider": provider, "token": token, "jobs_at_verify": n}
    return None


if __name__ == "__main__":
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(verify, SEED))
    verified = [r for r in results if r]
    for (name, *_), r in zip(SEED, results):
        print(f"{'OK ' if r else '-- '}{name:24} {r['provider'] + '/' + r['token'] + ' (' + str(r['jobs_at_verify']) + ')' if r else 'no verified board'}")
    out = Path(__file__).resolve().parent.parent / "backend/healthsurface/companies.json"
    out.write_text(json.dumps(verified, indent=1) + "\n")
    print(f"{len(verified)} verified of {len(SEED)} -> {out}", file=sys.stderr)
