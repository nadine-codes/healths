"""App-wide settings. Change the app name here only."""
import os

APP_NAME = "HealthSurface"
TAGLINE = "Health news, funding and jobs, labeled by source type."
DISCLAIMER = "This is a reading list, not medical advice."

CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
USER_AGENT = f"{APP_NAME}/1.0 (+https://github.com/nadine-codes/healths) {CONTACT_EMAIL}".strip()

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
    "medcity": {"name": "MedCity News", "label": "Reported news", "free_to_read": True, "commercial": True,
                "feed": "https://medcitynews.com/feed/"},
    "fierce_healthcare": {"name": "Fierce Healthcare", "label": "Reported news", "free_to_read": True, "commercial": True,
                          "feed": "https://www.fiercehealthcare.com/rss/xml"},
    "biopharma_dive": {"name": "BioPharma Dive", "label": "Reported news", "free_to_read": True, "commercial": True,
                       "feed": "https://www.biopharmadive.com/feeds/news/"},
    "healthcare_dive": {"name": "Healthcare Dive", "label": "Reported news", "free_to_read": True, "commercial": True,
                        "feed": "https://www.healthcaredive.com/feeds/news/"},
}

# PubMed query: health tech and translational topics our audience follows.
PUBMED_TERM = (
    '("digital health"[tiab] OR "artificial intelligence"[tiab] OR "machine learning"[tiab] '
    'OR telemedicine[tiab] OR "wearable"[tiab] OR GLP-1[tiab] OR longevity[tiab]) '
    'AND (randomized controlled trial[pt] OR meta-analysis[pt] OR systematic review[pt])'
)
