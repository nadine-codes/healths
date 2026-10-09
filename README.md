# HealthSurface

**Health news, funding and jobs, labeled by source type.**

Live: https://d27dduaz3tjeg8.cloudfront.net

HealthSurface is a read-only reading list for people who follow health and health tech: clinicians and administrators moving into health tech, founders, operators, investors and analysts. Every news story carries a **Source type** label (Press release, Preprint, Peer-reviewed study, Regulatory action, Reported news), so readers can tell a company announcement from a preprint or an FDA action at a glance. All three tabs share the same Sector and Focus area tags:

1. **News**: stories from openFDA, medRxiv, PubMed, The Conversation, and the CMS and CDC newsrooms, each with a short summary in our own words.
2. **Funding**: SEC Form D filings from health companies, NIH small business research grants, plus funding rounds announced in the news.
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

# 3. Create the Bedrock guardrail (once); prints its id
./scripts/create_guardrail.sh

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

## Ask chat (built from chatbotfirst.md; off until the owner enables it)

An "Ask what's new" chat, opened from the floating logo button at the bottom right of every tab, answers questions only from stored stories, funding records and job posts, and lists its sources with their Source type. `POST /api/ask` runs in its own Lambda (`handlers/ask_api.py`); the logic lives in `healthsurface/ask.py` with no AWS code.

- **Order of checks:** input check, rate limits (1 request per second with burst 3 on the route; 6 per minute and 50 per day per visitor, raised from the spec's 3 and 10 so judges never hit them; 1,000 requests and 300 model-backed answers per day overall), rule check for advice and personal questions (refusal with cited stories, no model call), 24-hour answer cache, Ask guardrail on the question, retrieval (up to 8 items by keyword, Sector and Focus area), one Amazon Nova Lite call (`amazon.nova-lite-v1:0`, in-region, 300 output tokens), guardrail on the answer, then only cited ids from the retrieved set are kept.
- **Kill switch:** `aws dynamodb put-item --table-name <MetaTable> --item '{"id":{"S":"ask_settings"},"enabled":{"BOOL":false}}'` turns it off without a deploy; the page hides the chat button. Deploy default: `AskEnabled=false`.
- **Guardrail:** `scripts/create_ask_guardrail.sh` (denied topics: medical advice, diagnosis; prompt-attack filter; personal details masked in questions only, since answers name cities from job posts).
- **Deviations from the spec:** Lambda reserved concurrency is not possible on this account (concurrency limit 10, all of it must stay unreserved), so the route throttle caps concurrency; HTTP APIs have no usage plans, so the 1,000-a-day quota is a DynamoDB counter. Alarm: more than 500 Ask invocations in an hour emails the owner. A second AWS Budget alerts at $50.
- **Privacy:** no question text is stored or logged (logs carry the outcome state only; the cache key and the rate-limit key are hashes; the rate-limit key is a salted, daily IP hash that expires within two days). Bedrock model invocation logging is off. Amazon states that Bedrock does not store or log prompts and completions and does not use them to train models; Ask uses the in-region model ID so requests stay in us-east-1. See `frontend/privacy.html` and `docs/BREACH_RESPONSE.md`.
- **Legal review: not done yet.** The likely exposure is the FTC Act, the FTC Health Breach Notification Rule, state consumer health data laws and CCPA/CPRA, not HIPAA. The design collects as little as possible and shares nothing.
- **Checks:** `backend/tests/test_ask.py`; 10-question Nova Lite check in `proof/12-ask-10-question-check.txt`.

## Sources

| Source | Used for | Label | Terms status |
|---|---|---|---|
| openFDA drugs@FDA, device 510(k) and De Novo | Approvals and clearances | Regulatory action | CC0 public domain. Links go to FDA accessdata pages. |
| FDA press announcements RSS | Press announcements | Regulatory action | US government work. **Currently blocked from AWS IP ranges (HTTP 404)**, so the fetcher logs and skips it. |
| medRxiv API (api.biorxiv.org) | Preprints | Preprint | Metadata API for reuse. We store title, link, date, category and the license field, never the abstract. |
| PubMed E-utilities | RCTs, meta-analyses and systematic reviews on health tech topics | Peer-reviewed study | NCBI policy followed: `tool` and `email` sent, under 3 requests per second, and NCBI's disclaimer and copyright notice linked in the site footer as their scripting guidelines require. Title, journal, date and link only; no abstracts, since publishers may hold copyright. Links go to PubMed Central when an open copy exists. |
| SEC EDGAR full-text search and Form D XML | Funding | n/a | SEC fair access: identifying User-Agent, under 10 requests per second. |
| The Conversation (US Health) Atom feed | Research-based analysis by academics | Reported news | Published under [CC BY-ND 4.0](https://theconversation.com/us/republishing-guidelines). We do not republish articles; we show the headline and link, credited "The Conversation". |
| CMS Newsroom RSS | Agency press releases and news alerts | Press release | US government work, public domain. The feed packs each title into an HTML anchor in `<link>`, so it is unpacked in code. |
| CDC Newsroom RSS (tools.cdc.gov) | Agency press releases | Press release | US government work, public domain. Feed links go through a download redirect, which is resolved to the cdc.gov page. |
| NIH RePORTER API | SBIR and STTR small business research grants | n/a (Funding, round "Grant") | US government data, public domain. Amount, date, awardee and NIH institute, linked to the RePORTER project page. |
| PR Newswire | n/a | n/a | **Not used.** Its [terms](https://www.prnewswire.com/terms-of-use/) ban robots and republishing without written permission. |
| Business Wire | n/a | n/a | **Not used.** Its [terms](https://www.businesswire.com/terms-of-use) limit the site to reading releases and retrieving feeds and bar commercial activity and aggregating its content without written consent. It also blocks automated requests. |
| GlobeNewswire | n/a | n/a | **Not used.** It publishes no terms for reusing its feeds; republishing goes through partner agreements. |
| Company announcements (`announced_rounds.json`) | Funding rounds announced before a Form D appears | n/a (Funding, "Company announcement") | Entered and checked by hand, linked to the company's own announcement page. Only facts (company, amount, round, date, investors) that the linked page states; no text is copied. No automated fetching. |
| SBIR.gov API | n/a | n/a | Returns 403 to our requests. NIH RePORTER covers the HHS share of these awards. |
| MedCity News RSS | n/a | n/a | **Disabled.** Its [terms of service](https://medcitynews.com/medcitizen-terms-of-service/) prohibit robots or automated access, republishing, and commercial use without written consent. All stored MedCity items were deleted. |
| BioPharma Dive, Healthcare Dive, Fierce Healthcare RSS | n/a | n/a | **Disabled.** They block AWS IPs, and their terms were not cleared for this use. |
| MobiHealthNews, NIH news releases | n/a | n/a | Return 403 to automated requests. Not used. |
| Medical News Today | n/a | n/a | Not added. It is consumer health content and outside our scope. |
| STAT, Endpoints | n/a | n/a | Not used (paywalled). |
| Greenhouse, Lever, Ashby public job board APIs | Jobs | n/a | Official public, no-login endpoints for each employer's published postings. robots.txt allows the API paths. Lever asks for a 1 second crawl delay, which we follow. No published terms restrict reading public postings: Lever's and Ashby's terms bind their customers, and Greenhouse publishes no API or job board terms. The docs describe the APIs as built for a company's own careers page, so third-party use is permitted by silence, not explicitly granted. We keep only the title, location, date and link (no descriptions), link every job to the employer's own posting, and remove closed jobs on each run. |
| Remote OK API | Remote jobs (health-related only) | n/a | The API terms (returned in the feed) require naming "Remote OK" as the source and a followed link back to the posting on remoteok.com. Every card says "Via Remote OK" and links to that job's Remote OK page. We do not use their logo. |
| ClinicalTrials.gov, Europe PMC, OpenAlex | n/a | n/a | Not built tonight. |

**Free-to-read check** (commercial links only): robots.txt, then the HTTP status (401, 402 and 403 are skipped), then the JSON-LD `isAccessibleForFree`, then obvious subscribe-wall markers. The checker reads at most the first 150 KB of HTML and stores none of it. Skipped items and reasons are logged and kept in the last run report.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

The tests cover taxonomy shape, model-reply validation (rejected sectors, dropped invented focus areas, banned hype words and em-dashes), the funding fact check, the keyword job classifier, the daily brief keeping each story's own label, Form D parsing, URL dedupe, paywall markers and board-token slugs.

## License

MIT. See [LICENSE](LICENSE).
