# Builder Center submission draft

Paste into the HealthSurface project on AWS Builder Center. Add both tags before Oct 2, 11:59 PM PT.

**Tags:** #commercial-potential #startups

**Live app:** https://d27dduaz3tjeg8.cloudfront.net (no login)
**Code:** https://github.com/nadine-codes/healths

## What it is
HealthSurface is a free, read-only reading list for people who follow health and health tech: clinicians and administrators moving into health tech, founders, operators, investors and analysts. Health news mixes company press releases, preprints, peer-reviewed studies and FDA actions in one stream, and they are hard to tell apart. HealthSurface labels every story by **Source type** (Press release, Preprint, Peer-reviewed study, Regulatory action, Reported news), so a reader can see what kind of source it is before clicking.

Three tabs share the same Sector and Focus area tags:
1. **News** from openFDA, medRxiv, PubMed, KFF Health News, The Conversation and the CMS and CDC newsrooms, each with a two-sentence summary in our own words and a daily brief.
2. **Funding** from SEC Form D filings, NIH small business grants and funding announcements in the news. A round and investors appear only when the source states them.
3. **Jobs** from verified company job boards (Greenhouse, Lever, Ashby) and Remote OK, filterable by function, job type, employment type, country and remote.

It is not medical advice. There are no accounts and no personal data, and every item links to its original source.

## How it is built on AWS
- **Amazon CloudFront + S3** (Origin Access Control) serve the static site, and route `/api/*` to **API Gateway (HTTP API)** on the same domain, so there is one public URL and no CORS.
- **AWS Lambda** (Python 3.14, arm64): an ingest function and a read-only API function.
- **Amazon DynamoDB**: one table each for news, funding, jobs and run metadata.
- **Amazon Bedrock**: Amazon Nova Lite tags sector and focus areas, writes the summary and spots funding announcements. **Bedrock Guardrails** check every model output for medical advice and dosing.
- **EventBridge Scheduler** refreshes twice a day with retries off.
- **AWS SAM** for all infrastructure as code, and an **AWS Budget** alert at $25.

**Code versus AI:** code decides the source type label, links, dates, dedupe, free-to-read checks and job board matching. The model decides tags and summaries, and every reply is validated against the taxonomy. Funding facts are checked in code: the amount, round and investors must appear in the source text, which stopped the model from calling a $1B pharma partnership a "Series B".

## How the coding agent helped
Claude Code (Claude Opus 5.5) built and shipped the app in one evening from a written brief. It connected to the AWS account with `aws login` (console sign-in) and ran every AWS step itself: the identity check, the Bedrock model check and test call, the budget, the guardrail, each `sam deploy`, the S3 sync and CloudFront invalidations. It tracked each build step as a Linear issue through the Linear MCP connector, deployed after every step so there was always a live version, and kept a friction log.

Things the agent caught and fixed along the way:
- A new-account Lambda concurrency quota rolled back the first deploy, so it replaced reserved concurrency with a DynamoDB run lock.
- Bedrock returned "account is being verified". It built a keyword fallback classifier so the site worked while verification was pending.
- PubMed's sort date was months in the future for some journals, so it switched to the indexed date.
- SEC EDGAR rejected its User-Agent format, so it matched the exact format SEC asks for.
- A source terms review: it disabled a news feed whose terms ban automated access, deleted the stored items, and replaced it with sources whose licenses allow this use. It added the credits that NCBI and Remote OK require.

**Proof of the agent connection:** `proof/` in the repo (identity check, Bedrock calls, deploy logs, live URL checks, screenshots), summarized in `PROCESS.md`. Full timeline in `PROCESS.md` and `FRICTION_LOG.md`.

## Where it is headed (Startups lane)
- **Next:** an MCP server and an Alexa+ voice briefing that reuse the same classification module (it has no AWS code in it for this reason), ClinicalTrials.gov and Europe PMC sources, and email digests by focus area.
- **Business model:** free reading list, paid alerts and digests for investors and operators (new Form D filings and hiring signals by sector), and job postings for health companies.
- **Licensing before revenue:** KFF Health News is CC BY-NC-ND, so it would be licensed or dropped before any paid tier. All other sources are public domain, open metadata APIs, or CC BY-ND with headline-and-link use.
- **Cost:** about $0.0001 per story in model tokens. A full refresh costs about a cent.
