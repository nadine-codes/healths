"""App-wide settings. Change the app name here only."""
import os

APP_NAME = "HealthSurface"
TAGLINE = "Health news, funding and jobs, labeled by source type."
DISCLAIMER = "This is a reading list, not medical advice."

CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
USER_AGENT = f"{APP_NAME}/1.0 (+https://github.com/nadine-codes/healths) {CONTACT_EMAIL}".strip()

# Stories whose headline or description match this are never pulled or shown.
# Covers suicide, suicides, suicidal and suicidality.
BLOCKED_STORY_TERMS = r"\bsuicid(e|es|al|ality)\b"

# Per-run hard caps on Bedrock classification (cost guardrail).
MAX_NEW_STORIES_PER_RUN = 100
MAX_NEW_JOBS_PER_RUN = 200

# Every news source, its evidence label (decided by code, not AI) and whether
# visitors can read it without paying or signing up.
NEWS_SOURCES = {
    "fda_press": {"name": "FDA Press Announcements", "label": "Regulatory action", "free_to_read": True, "commercial": False},
    "openfda_drugs": {"name": "openFDA Drug Approvals", "label": "Regulatory action", "free_to_read": True, "commercial": False},
    "openfda_devices": {"name": "openFDA Device Clearances", "label": "Regulatory action", "free_to_read": True, "commercial": False},
    "medrxiv": {"name": "medRxiv", "label": "Preprint", "free_to_read": True, "commercial": False},
    "pubmed": {"name": "PubMed", "label": "Peer-reviewed study", "free_to_read": True, "commercial": False},
    # Open-license newsrooms. We show only headline, link, date and our own summary, credited by name.
    "kff_health_news": {"name": "KFF Health News", "label": "Reported news", "free_to_read": True, "commercial": False,
                        "feed": "https://kffhealthnews.org/feed/",
                        "terms": "CC BY-NC-ND 4.0; RSS offered for ingestion (kffhealthnews.org/syndication)"},
    "the_conversation": {"name": "The Conversation", "label": "Reported news", "free_to_read": True, "commercial": False,
                         "feed": "https://theconversation.com/us/health/articles.atom",
                         "terms": "CC BY-ND 4.0 (theconversation.com/us/republishing-guidelines)"},
    "cms_newsroom": {"name": "CMS Newsroom", "label": "Press release", "free_to_read": True, "commercial": False,
                     "feed": "https://www.cms.gov/newsroom/rss-feeds", "terms": "US government work, public domain"},
    "cdc_newsroom": {"name": "CDC Newsroom", "label": "Press release", "free_to_read": True, "commercial": False,
                     "feed": "https://tools.cdc.gov/api/v2/resources/media/132608.rss", "terms": "US government work, public domain"},
    # Commercial outlets are disabled. MedCity News terms prohibit automated access, republishing and
    # commercial use without consent; the others block AWS IPs and were not cleared. Kept for the record.
    "medcity": {"name": "MedCity News", "label": "Reported news", "free_to_read": True, "commercial": True,
                "enabled": False, "feed": "https://medcitynews.com/feed/"},
    "fierce_healthcare": {"name": "Fierce Healthcare", "label": "Reported news", "free_to_read": True, "commercial": True,
                          "enabled": False, "feed": "https://www.fiercehealthcare.com/rss/xml"},
    "biopharma_dive": {"name": "BioPharma Dive", "label": "Reported news", "free_to_read": True, "commercial": True,
                       "enabled": False, "feed": "https://www.biopharmadive.com/feeds/news/"},
    "healthcare_dive": {"name": "Healthcare Dive", "label": "Reported news", "free_to_read": True, "commercial": True,
                        "enabled": False, "feed": "https://www.healthcaredive.com/feeds/news/"},
}

# PubMed query: health tech and translational topics our audience follows.
PUBMED_TERM = (
    '("digital health"[tiab] OR "artificial intelligence"[tiab] OR "machine learning"[tiab] '
    'OR telemedicine[tiab] OR "wearable"[tiab] OR GLP-1[tiab] OR longevity[tiab]) '
    'AND (randomized controlled trial[pt] OR meta-analysis[pt] OR systematic review[pt])'
)
