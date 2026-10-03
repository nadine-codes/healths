# HealthSurface

**Health news, funding and jobs, labeled by source type.**

Live: https://d27dduaz3tjeg8.cloudfront.net

HealthSurface is a read-only reading list for people who follow health and health tech: clinicians and administrators moving into health tech, founders, operators, investors and analysts. Every news story carries a **Source type** label (Press release, Preprint, Peer-reviewed study, Regulatory action, Reported news), so readers can tell a company announcement from a preprint or an FDA action at a glance. All three tabs share the same Sector and Focus area tags:

1. **News**: stories from FDA, openFDA, medRxiv, PubMed and free industry news, each with a short summary in our own words.
2. **Funding**: SEC Form D filings from health companies, plus funding rounds announced in the news.
3. **Jobs**: open roles from verified company job boards (Greenhouse, Lever, Ashby) and RemoteOK, filterable by function, job type, employment type, sector, focus area and remote.

This is a reading list, not medical advice. There are no accounts, no personal data and no chat. Every item links to its original source.

Built for the AWS "Zero to Shipped" hackathon.

## Architecture

```
EventBridge Scheduler (06:00 and 18:00 UTC, no retries)
        │
        ▼
 Ingest Lambda ──► sources/ (FDA, openFDA, medRxiv, PubMed, RSS, SEC EDGAR, job boards, RemoteOK)
        │      ──► classify.py (pure Python) ──► Bedrock Nova Lite + Guardrail (output check)
        ▼
    DynamoDB (news, funding, jobs, meta)
        ▲
   API Lambda (read-only JSON) ◄── HTTP API ◄── CloudFront /api/*  (5 min cache)
                                               CloudFront /*  ──► S3 (static HTML/CSS/JS)
```

- **One domain**: CloudFront serves the static site from a private S3 bucket (Origin Access Control) and routes `/api/*` to API Gateway. There is no CORS and only one public URL.
- **Code vs AI**: code decides the source type label (from which source an item came), the link, date, dedupe (URL hash or job id), free-to-read checks and job board matching. Nova decides the sector, focus areas, the summary, and whether a headline announces funding. Every model reply is validated against the taxonomy. Funding facts are then checked against the source text, so the amount, round and investors must appear there.
- **Classification module**: `backend/healthsurface/classify.py` has no AWS code. The model is passed in as `invoke(system, user) -> str`, so the same module can back an MCP server or voice briefing later.
- **Fallback**: if Bedrock fails or a run hits its cap, a keyword classifier fills the same fields, and the item is retried with the model on a later run.

## Repository layout

```
template.yaml                  SAM infrastructure (S3, CloudFront, HTTP API, Lambda, DynamoDB, Scheduler)
backend/healthsurface/
  config.py                    App name, sources, per-source labels and free_to_read flags, caps
  taxonomy.json / taxonomy.py  Sectors, focus areas, source types, round stages, job taxonomy
  classify.py                  Prompts, validation, funding fact check, keyword fallback, daily brief
  companies.json               Verified job boards (written by scripts/verify_boards.py)
  sources/                     news.py, funding.py, jobs.py, http.py (stdlib only)
  handlers/                    ingest.py, api.py, bedrock.py, store.py (AWS code lives only here)
backend/tests/                 pytest unit tests
frontend/                      index.html, styles.css, app.js (no build step)
scripts/verify_boards.py       Verifies Greenhouse, Lever and Ashby tokens by calling each board
proof/                         AWS identity, Bedrock and deploy logs, screenshots
```

## Setup and run

Requirements: AWS CLI v2, AWS SAM CLI, Python 3.14, and an AWS account with Amazon Nova enabled in us-east-1.

```bash
# 1. Install test dependencies
python3 -m venv .venv && .venv/bin/pip install boto3 pytest

# 2. Run the tests
cd backend && ../.venv/bin/python -m pytest -q && cd ..

# 3. Create a Bedrock guardrail (once) and note its id
aws bedrock create-guardrail --name healthsurface-guardrail ...   # see PROCESS.md for the policy used
aws bedrock create-guardrail-version --guardrail-identifier <id>

# 4. Build and deploy (the schedule ships DISABLED unless you pass ScheduleState=ENABLED)
sam build
sam deploy --guided --parameter-overrides \
  ContactEmail=<you@example.com> GuardrailId=<id> GuardrailVersion=1 ScheduleState=ENABLED

# 5. Upload the front end
aws s3 sync frontend/ s3://<SiteBucketName>/ --delete
aws cloudfront create-invalidation --distribution-id <DistributionId> --paths '/*'

# 6. Run a first ingest (or wait for the schedule)
aws lambda invoke --function-name <IngestFunctionName> --cli-read-timeout 0 out.json
```

`ContactEmail` goes only into the User-Agent and `email` parameters that PubMed and SEC EDGAR require. It is a deploy parameter and never committed.

To refresh the verified job boards: `python3 scripts/verify_boards.py`.

## Cost guardrails

- An AWS Budget alert at $25 per month (actual over 100%, forecast over 80%).
- Only new items are classified. Dedupe is by URL hash (news), filing accession number (Form D) or job id.
- Hard caps per run: 100 stories and 200 jobs sent to Bedrock. Everything else uses the keyword fallback until a later run.
- The schedule runs twice a day with retries off, and a DynamoDB lock prevents overlapping runs.
- Nova Lite costs about $0.0001 per story. A first full run cost about $0.01 in model tokens plus the guardrail checks. Expected total through Oct 23 is well under $5.
- The API is cached at CloudFront for 5 minutes and throttled at 20 requests per second (burst 50).

## Sources

| Source | Used for | Label | Terms status |
|---|---|---|---|
| openFDA drugs@FDA, device 510(k) and De Novo | Approvals and clearances | Regulatory action | CC0 public domain. Links go to FDA accessdata pages. |
| FDA press announcements RSS | Press announcements | Regulatory action | US government work. **Currently blocked from AWS IP ranges (HTTP 404)**, so the fetcher logs and skips it. |
| medRxiv API (api.biorxiv.org) | Preprints | Preprint | Metadata API for reuse. We store title, link, date, category and the license field, never the abstract. |
| PubMed E-utilities | RCTs, meta-analyses and systematic reviews on health tech topics | Peer-reviewed study | NCBI policy followed (`tool` and `email` sent, under 3 requests per second). Title, journal, date and link only; no abstracts. Links go to PubMed Central when an open copy exists. |
| SEC EDGAR full-text search and Form D XML | Funding | n/a | SEC fair access: identifying User-Agent, under 10 requests per second. |
| MedCity News RSS | Industry news | Reported news | robots.txt allows feed and article paths. Headline, link, date and our own summary only. Each article URL passes the free-to-read check. |
| BioPharma Dive, Healthcare Dive RSS | Industry news | Reported news | Feeds load, but article pages return 403 to AWS IPs, so the free-to-read rule skips every item. Kept in config and logged. |
| Fierce Healthcare RSS | Industry news | Reported news | Returns 403 to AWS IPs. Logged and skipped. |
| MobiHealthNews, NIH news releases | n/a | n/a | Return 403 to automated requests. Not used. |
| Medical News Today | n/a | n/a | Not added. It is consumer health content and outside our scope tonight. |
| STAT, Endpoints | n/a | n/a | Not used (paywalled). |
| Greenhouse, Lever, Ashby public job board APIs | Jobs | n/a | Public APIs meant for embedding a company's own board. Only tokens verified to return jobs are used. |
| RemoteOK API | Remote jobs (health-related only) | n/a | Their terms require crediting RemoteOK and linking to the original posting, and every card does both. |
| ClinicalTrials.gov, Europe PMC, OpenAlex, NIH RePORTER, SBIR.gov | n/a | n/a | Not built tonight. |

**Free-to-read check** (commercial links only): robots.txt, then the HTTP status (401, 402 and 403 are skipped), then the JSON-LD `isAccessibleForFree`, then obvious subscribe-wall markers. The checker reads at most the first 150 KB of HTML and stores none of it. Skipped items and reasons are logged and kept in the last run report.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

The tests cover taxonomy shape, model-reply validation (rejected sectors, dropped invented focus areas, banned hype words and em-dashes), the funding fact check, the keyword job classifier, the daily brief keeping each story's own label, Form D parsing, URL dedupe, paywall markers and board-token slugs.

## License

MIT. See [LICENSE](LICENSE).
