"""Classification and summarizing logic.

Pure Python with no AWS code: the model call is passed in as `invoke(system, user) -> str`,
so the same functions can be reused later by an MCP server or voice briefing.

Code decides the evidence label, link, date and dedupe. The model decides sector, focus
areas, the own-words summary and whether a headline announces funding. Anything the model
returns is validated against the taxonomy and rejected if it does not fit. When no model is
available (or it fails), a keyword fallback fills the same fields so the site still works.
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from . import config
from . import taxonomy as tx

Invoke = Callable[[str, str], str]

SYSTEM_PROMPT = (
    "You label health news for a reading list. You never give medical advice, dosing, or "
    "treatment recommendations. You never judge how good the evidence is; words like proven, "
    "breakthrough, or high-quality are not allowed. Summaries are neutral, in your own words, "
    "and at most two sentences. Only state facts present in the input. Reply with JSON only."
)

BANNED_WORDS = re.compile(r"\b(proven|proves|breakthrough|miracle|cure[sd]?|high[- ]quality evidence)\b", re.I)
AMOUNT_RE = re.compile(r"\$\s?\d+(?:\.\d+)?\s?(?:million|billion|[mb]n?)\b", re.I)


_BLOCKED = re.compile(config.BLOCKED_STORY_TERMS, re.I)


def is_blocked_story(*texts: str) -> bool:
    """True when a story touches a topic we never pull (see config.BLOCKED_STORY_TERMS)."""
    return any(_BLOCKED.search(t or "") for t in texts)


# ---------- prompts ----------

def story_prompt(item: dict) -> str:
    return (
        f"Sectors (pick exactly one): {json.dumps(tx.SECTORS)}\n"
        f"Focus areas (pick one to three that clearly apply, or the single closest): {json.dumps(tx.FOCUS_AREAS)}\n"
        f"Round stages: {json.dumps(tx.ROUND_STAGES)}\n\n"
        f"Source: {item.get('source_name')}\nSource type: {item.get('label')}\n"
        f"Headline: {item.get('title')}\nDescription: {(item.get('description') or '')[:1200]}\n\n"
        "Return JSON with keys: sector, focus_areas (array), summary (max 2 sentences, own words, "
        "no medical advice), confidence (0 to 1), is_funding_announcement (true only if the headline "
        "or description says a company raised money, closed a round, or was acquired), funding "
        "(object or null with keys company, amount_usd (number or null), round_stage (from the list "
        "or null), date (YYYY-MM-DD or null), investors (array)). Leave any funding field null "
        "unless it is stated. Never guess an amount."
    )


def job_prompt(job: dict) -> str:
    return (
        f"Job types: {json.dumps(tx.JOB_TYPES)}\n"
        f"Employment types: {json.dumps(tx.EMPLOYMENT_TYPES)}\n"
        f"Seniority: {json.dumps(tx.SENIORITY)}\n\n"
        f"Title: {job.get('title')}\nCompany: {job.get('company')}\n"
        f"Posting excerpt: {(job.get('text') or '')[:800]}\n\n"
        "Return JSON with keys: job_type, employment_type, seniority. Copy each value exactly from its "
        "list. Clinicians (nurses, physicians, therapists, pharmacists) are Clinical Product Specialist "
        "unless a more specific clinical type fits; recruiters are People and Recruiting."
    )


def brief_prompt(stories: list[dict]) -> str:
    lines = [f"[{i}] ({s['label']}) {s['title']}" for i, s in enumerate(stories)]
    return (
        "Pick the 6 most notable stories for a general reader interested in health and health tech. "
        "Prefer a mix of source types and topics, and avoid near-duplicates. "
        'Return JSON: {"picks": [<story numbers in order of importance>]}\n\n' + "\n".join(lines)
    )


# ---------- parsing and validation ----------

def parse_json(text: str) -> dict:
    """Extract the first JSON object from a model reply (tolerates code fences)."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("no JSON object in reply")
    return json.loads(match.group(0))


def clean_summary(text: str) -> str:
    text = " ".join((text or "").split()).replace("—", ", ").replace("–", "-")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    text = " ".join(sentences[:2])
    if not text or BANNED_WORDS.search(text):
        raise ValueError("summary empty or uses banned wording")
    return text[:400]


def validate_story(raw: dict) -> dict:
    sector = raw.get("sector")
    if sector not in tx.SECTORS:
        raise ValueError(f"bad sector: {sector!r}")
    # Values outside the taxonomy are dropped. An empty list is allowed (e.g. agency policy news).
    focus = [f for f in (raw.get("focus_areas") or []) if f in tx.FOCUS_AREAS]
    out = {
        "sector": sector,
        "focus_areas": list(dict.fromkeys(focus))[:3],
        "summary": clean_summary(raw.get("summary", "")),
        "confidence": max(0.0, min(1.0, float(raw.get("confidence") or 0))),
        "is_funding_announcement": bool(raw.get("is_funding_announcement")),
        "funding": None,
    }
    if out["is_funding_announcement"]:
        out["funding"] = validate_funding(raw.get("funding") or {})
    return out


def validate_funding(raw: dict) -> Optional[dict]:
    company = (raw.get("company") or "").strip()
    if not company:
        return None
    amount = raw.get("amount_usd")
    try:
        amount = float(amount) if amount not in (None, "") else None
    except (TypeError, ValueError):
        amount = None
    stage = raw.get("round_stage") if raw.get("round_stage") in tx.ROUND_STAGES else None
    date = raw.get("date") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw.get("date") or "")) else None
    investors = [str(i).strip() for i in (raw.get("investors") or []) if str(i).strip()][:10]
    return {"company": company[:120], "amount_usd": amount, "round_stage": stage, "date": date, "investors": investors}


def validate_job(raw: dict, title: str = "") -> dict:
    job_type = raw.get("job_type")
    if job_type not in tx.JOB_TYPES or job_type == "Other":
        # Off-list or "Other" answers defer to the keyword rules, which map to the exact list.
        job_type = rule_classify_job({"title": title})["job_type"]
    emp = raw.get("employment_type")
    if emp not in tx.EMPLOYMENT_TYPES:
        raise ValueError(f"bad employment type: {emp!r}")
    seniority = raw.get("seniority") if raw.get("seniority") in tx.SENIORITY else None
    return {
        "job_type": job_type,
        "function_group": tx.function_group_for(job_type),
        "employment_type": emp,
        "seniority": seniority,
    }


# ---------- keyword fallback (no model) ----------

SECTOR_KEYWORDS = [
    ("Policy and Regulation", r"\b(policy|congress|cms|medicare|medicaid|legislat|rule|regulat|hhs|guidance|advisory committee)\b"),
    ("Health AI", r"\b(ai|artificial intelligence|machine learning|deep learning|llm|large language|algorithm)\b"),
    ("Peptides", r"\b(peptide|glp-1|semaglutide|tirzepatide)\b"),
    ("Supplements and Nutraceuticals", r"\b(supplement|vitamin|nutraceutical|probiotic|omega-3)\b"),
    ("Health Data and IT", r"\b(ehr|electronic health record|interoperab|data platform|cyber|epic|cerner|health it)\b"),
    ("Care Delivery and Payers", r"\b(hospital|health system|payer|insurer|medicare advantage|clinic|telehealth|telemedicine|primary care)\b"),
    ("Med Tech", r"\b(device|implant|510\(k\)|catheter|stent|valve|diagnostic|imaging|surgical|wearable)\b"),
    ("Pharma", r"\b(drug|tablet|injection|nda|anda|pharma|dose|capsule|biosimilar)\b"),
    ("Life Sciences and Biotech", r"\b(biotech|gene|cell therapy|antibody|crispr|genom|protein|trial|vaccine)\b"),
    ("Health Tech", r"\b(app|platform|digital|startup|software|virtual)\b"),
]

FOCUS_KEYWORDS = [
    ("Longevity and healthspan", r"\b(longevity|aging|ageing|healthspan|lifespan)\b"),
    ("Hormones", r"\b(hormone|testosterone|estrogen|menopause|thyroid)\b"),
    ("Sleep", r"\b(sleep|insomnia|apnea)\b"),
    ("Fitness and recovery", r"\b(exercise|fitness|physical activity|recovery|rehabilitation)\b"),
    ("Women's health", r"\b(women|maternal|pregnan|fertility|menopause|ovarian|cervical|breast)\b"),
    ("Men's health", r"\b(men's|prostate|erectile|testosterone)\b"),
    ("Metabolic health and obesity", r"\b(obesity|weight|metabolic|glp-1|semaglutide|tirzepatide)\b"),
    ("Diabetes", r"\b(diabet|insulin|glucose|a1c)\b"),
    ("Nutrition and gut health", r"\b(nutrition|diet|gut|microbiome|food)\b"),
    ("Mental health", r"\b(mental|depress|anxiety|psychiatr|suicid|substance|opioid|addiction)\b"),
    ("Neurology and brain health", r"\b(brain|neuro|alzheimer|parkinson|stroke|dementia|epilep|migraine)\b"),
    ("Cardiovascular", r"\b(heart|cardi|hypertension|blood pressure|cholesterol|vascular|valve)\b"),
    ("Cancer and oncology", r"\b(cancer|oncolog|tumou?r|leukemia|lymphoma|carcinoma)\b"),
    ("Immunology and autoimmune", r"\b(immun|autoimmune|lupus|arthritis|psoriasis|allerg|epinephrine)\b"),
    ("Infectious disease", r"\b(infect|virus|viral|covid|influenza|vaccine|antibiotic|hiv|measles)\b"),
    ("Skin and dermatology", r"\b(skin|derma|eczema|acne|melanoma)\b"),
    ("Pain and chronic conditions", r"\b(pain|chronic|fibromyalgia|arthritis)\b"),
    ("Genetics and precision medicine", r"\b(gene|genetic|genom|precision|crispr|variant)\b"),
    ("Pediatrics and family health", r"\b(child|children|pediatric|paediatric|infant|adolescent|newborn)\b"),
    ("Senior care", r"\b(older adults|elderly|senior|nursing home|aging)\b"),
]

FUNDING_RE = re.compile(
    r"\b(raises?|raised|closes?|closed|secures?|secured|lands?|nabs?|bags?)\b[^.]*?(\$\s?\d|\b(round|funding|financing|seed|series [a-z])\b)"
    r"|\b(acquires|acquired|to acquire)\b", re.I)

SOURCE_SUMMARIES = {
    "Regulatory action": "An official notice from the FDA about this product or topic.",
    "Preprint": "A research paper posted before peer review, so its findings may still change.",
    "Peer-reviewed study": "A study published in a peer-reviewed journal.",
    "Press release": "An announcement written by the organization itself.",
    "Reported news": "A news report from a health industry outlet.",
}


NOISE_RE = re.compile(r"(u\.s\. )?food and drug administration|\bfda\b", re.I)


def rule_classify_story(item: dict) -> dict:
    text = NOISE_RE.sub(" ", f"{item.get('title', '')} {item.get('description', '')} {item.get('category', '')}")
    sector = next((s for s, rx in SECTOR_KEYWORDS if re.search(rx, text, re.I)), None)
    if not sector:
        sector = "Policy and Regulation" if item.get("label") == "Regulatory action" else "Life Sciences and Biotech"
    focus = [f for f, rx in FOCUS_KEYWORDS if re.search(rx, text, re.I)][:3]
    detail = item.get("summary_hint") or SOURCE_SUMMARIES.get(item.get("label"), "")
    return {
        "sector": sector,
        "focus_areas": focus,
        "summary": detail,
        "confidence": 0.3,
        "is_funding_announcement": bool(FUNDING_RE.search(item.get("title", ""))),
        "funding": None,
    }


JOB_TYPE_KEYWORDS = [
    ("UX Researcher", r"ux research|user research"),
    ("UX/UI Product Designer", r"product design|ux|ui designer|interaction design"),
    ("Brand Designer", r"brand design"),
    ("Graphic Designer", r"graphic design|visual design"),
    ("Marketing Designer", r"marketing design|creative design"),
    ("AI Engineer", r"machine learning|\bml\b|\bai\b|applied scientist|llm"),
    ("Data and Analytics", r"data scien|data engineer|analytics|analyst|biostatistic"),
    ("DevOps and Security", r"devops|site reliability|\bsre\b|security|infrastructure|platform engineer|cloud"),
    ("QA and Test", r"\bqa\b|quality assurance engineer|test engineer|sdet"),
    ("UI Engineer", r"front[- ]?end|ui engineer|ios|android|mobile engineer"),
    ("Software Engineer", r"software|engineer|developer|backend|full[- ]?stack"),
    ("Product Manager", r"product manager|product lead|product owner|head of product"),
    ("Project or Program Manager", r"program manager|project manager|tpm"),
    ("Product Marketing", r"product marketing"),
    ("Growth and Lifecycle Marketing", r"growth|lifecycle|performance marketing|demand gen|marketing"),
    ("Content and Editorial", r"content|editor|writer|copywrit"),
    ("Social Media and Community", r"social media|community"),
    ("PR and Communications", r"communications|\bpr\b|public relations"),
    ("Solutions and Sales Engineering", r"solutions engineer|sales engineer|solutions architect|solutions consultant"),
    ("Account Manager", r"accounts? manager|account executive|key account"),
    ("Customer Success Manager", r"customer success"),
    ("Implementation and Onboarding", r"implementation|onboarding|deployment"),
    ("Customer Support", r"support|customer service|member services|care coordinator"),
    ("Partnerships and Business Development", r"partnership|business development|\bbd\b|alliances"),
    ("Sales", r"sales|business development representative|\bsdr\b|\bbdr\b"),
    ("Medical Writing and Content", r"medical writ"),
    ("Medical Affairs and Science", r"medical affairs|medical science|msl|scientist|research associate|clinical scien"),
    ("Regulatory and Quality", r"regulatory|quality|compliance specialist|\bqms\b"),
    ("Health Informatics", r"informatic"),
    ("Clinical Operations", r"clinical operations|clinical trial|cra\b|study manager"),
    ("Clinical Product Specialist", r"nurse|\brn\b|physician|clinician|therapist|pharmacist|dietitian|psychiatr|psycholog|\bmd\b|\bdo\b|\bnp\b|clinical|coach|counselor|provider"),
    ("Finance and Accounting", r"financ|accountant|accounting|controller|fp&a|tax|equity"),
    ("People and Recruiting", r"recruit|talent|people|\bhr\b|human resources|learning|training|payroll"),
    ("Legal and Compliance", r"legal|counsel|attorney|compliance|privacy"),
    ("Executive and Admin", r"chief|\bceo\b|\bcfo\b|\bcto\b|vp\b|vice president|executive assistant|office manager|admin"),
    ("Operations and Strategy", r"operations|strategy|bizops|chief of staff|revenue cycle"),
]


def rule_classify_job(job: dict) -> dict:
    title = job.get("title", "")
    job_type = next((t for t, rx in JOB_TYPE_KEYWORDS if re.search(rx, title, re.I)), "Other")
    blob = f"{title} {job.get('commitment', '')}"
    if re.search(r"intern", blob, re.I):
        emp = "Internship"
    elif re.search(r"freelance", blob, re.I):
        emp = "Freelance"
    elif re.search(r"contract|temporary|temp\b|fixed[- ]term", blob, re.I):
        emp = "Contract"
    elif re.search(r"part[- ]time|per diem|prn", blob, re.I):
        emp = "Part-time"
    else:
        emp = "Full-time"
    seniority_rules = [
        ("Intern", r"intern"), ("Executive", r"chief|\bvp\b|vice president|head of"),
        ("Director", r"director"), ("Manager", r"manager"), ("Lead", r"lead|principal|staff"),
        ("Senior", r"senior|\bsr\.?\b|\biii\b"), ("Entry", r"junior|\bjr\.?\b|associate|entry|\bi\b"),
    ]
    seniority = next((s for s, rx in seniority_rules if re.search(rx, title, re.I)), "Mid")
    return {"job_type": job_type, "function_group": tx.function_group_for(job_type),
            "employment_type": emp, "seniority": seniority}


# ---------- entry points ----------

STAGE_PATTERNS = {
    "Pre-seed": r"pre-?seed", "Seed": r"\bseed\b", "Series A": r"series a\b", "Series B": r"series b\b",
    "Series C or later": r"series [c-h]\b", "Growth": r"growth (round|equity|financing)", "IPO": r"\bipo\b|initial public offering",
    "Acquisition": r"\bacquir", "Grant": r"\bgrant\b",
}


def _amount_values(text: str) -> list[float]:
    values = []
    for m in AMOUNT_RE.finditer(text):
        num = float(re.search(r"\d+(?:\.\d+)?", m.group(0)).group(0))
        values.append(num * (1e9 if re.search(r"b", m.group(0)[-8:], re.I) else 1e6))
    return values


def verify_funding(item: dict, result: dict) -> dict:
    """Code check on the model's funding facts: keep only what the source text states."""
    text = f"{item.get('title', '')} {item.get('description', '')}"
    if not result["is_funding_announcement"] or not FUNDING_RE.search(text):
        return {**result, "is_funding_announcement": False, "funding": None}
    f = result.get("funding")
    if not f:
        return result
    f = dict(f)
    if f.get("round_stage") and not re.search(STAGE_PATTERNS[f["round_stage"]], text, re.I):
        f["round_stage"] = None
    if f.get("amount_usd") is not None and not any(abs(v - f["amount_usd"]) < 0.06 * v for v in _amount_values(text)):
        f["amount_usd"] = None
    f["investors"] = [i for i in f.get("investors", []) if i.lower() in text.lower()]
    return {**result, "funding": f}


def classify_story(item: dict, invoke: Optional[Invoke] = None) -> tuple[dict, str]:
    """Return (classification, method) where method is 'model' or 'rules'."""
    if invoke:
        try:
            return verify_funding(item, validate_story(parse_json(invoke(SYSTEM_PROMPT, story_prompt(item))))), "model"
        except Exception:  # noqa: BLE001 - any model or validation failure falls back to rules
            pass
    return rule_classify_story(item), "rules"


def classify_job(job: dict, invoke: Optional[Invoke] = None) -> tuple[dict, str]:
    if invoke:
        try:
            return validate_job(parse_json(invoke(SYSTEM_PROMPT, job_prompt(job))), job.get("title", "")), "model2"
        except Exception:  # noqa: BLE001
            pass
    return rule_classify_job(job), "rules"


def todays_brief(stories: list[dict], invoke: Invoke) -> list[dict]:
    """5 to 7 bullets from stored stories. The model only chooses which stories; each bullet
    reuses that story's own summary, label and link, so a bullet can never carry the wrong label."""
    raw = parse_json(invoke(SYSTEM_PROMPT, brief_prompt(stories)))
    picks = [i for i in dict.fromkeys(raw.get("picks", [])) if isinstance(i, int) and 0 <= i < len(stories)][:7]
    bullets = [{"text": stories[i]["summary"].split(". ")[0].rstrip(".") + ".", "label": stories[i]["label"],
                "url": stories[i]["url"], "title": stories[i]["title"]} for i in picks if stories[i].get("summary")]
    if len(bullets) < 5:
        raise ValueError("brief too short")
    return bullets
