# Builder Center submission draft

Paste into the HealthSurface project on AWS Builder Center. Add both tags before Oct 2, 11:59 PM PT. Attach `proof/00-identity-and-bedrock.txt` (or a screenshot of it) and `proof/08-final-news.png`.

**Tags:** #commercial-potential #startups

---

# HealthSurface: health news, funding and jobs, labeled by source type

**Live:** https://d27dduaz3tjeg8.cloudfront.net (no login, opens straight to content)
**Code:** https://github.com/nadine-codes/healths (MIT)

## The problem
A headline says a new drug "cuts heart attack risk by 40%." Is that an FDA approval, a peer-reviewed trial, a preprint nobody has checked yet, or the company's own press release? Most health feeds do not tell you, and the difference is everything.

That gap hurts most for the people moving into health tech: nurses, pharmacists and hospital administrators retraining as product managers, analysts and founders. They need to follow the industry, spot who is raising money and find roles, and today that means a dozen tabs and a lot of guessing about what to trust.

## What HealthSurface does
One free reading list with three tabs that share the same Sector and Focus area tags:

- **News:** 160 stories from openFDA, medRxiv, PubMed, The Conversation, and the CMS and CDC newsrooms. Every story carries a **Source type** label: Press release, Preprint, Peer-reviewed study, Regulatory action or Reported news, with a tooltip saying what each one means. A daily "In focus" brief picks the top stories.
- **Funding:** 174 records from SEC Form D filings and NIH small business research grants. Amounts come from the filings themselves. A round or investor is shown only when a source states it.
- **Jobs:** 1,460 open roles at 69 health companies, from verified company job boards (Greenhouse, Lever, Ashby) and Remote OK. Filter by function, 36 job types, employment type, country and remote.

No accounts, no personal data, no medical advice. Every item links to its original source.

**Try it in one minute:** open the News tab and set Source type to "Preprint" to see what has not been peer reviewed yet. On Funding, filter Sector by "Health Tech". On Jobs, pick Function "Clinical and Health" and Country "United States".

## What is new here
**The label comes from code, not from the AI.** Language models are good at reading and bad at being trusted, so HealthSurface splits the work on purpose:

| Code decides (deterministic) | Amazon Nova decides (validated) |
|---|---|
| Source type label, from which source an item came | Sector and focus areas |
| Link, date, dedupe | A two-sentence summary in our own words |
| Free-to-read check (robots.txt, HTTP status, paywall markers) | Whether a headline announces funding |
| Job board verification and company matching | Job function, type and seniority |

Every model reply is checked against the taxonomy, and off-list answers are dropped one by one instead of trusted.

**Funding facts are fact-checked in code.** Early on, Nova labeled a $1B Sanofi and Regeneron partnership as a "Series B" round. Now a story only counts as funding if the text says raised, closed or secured, and the amount, round and investors must each appear in the source text. If they don't, they are left blank. The model cannot invent a number.

**Guardrails where they help, not where they hurt.** Amazon Bedrock Guardrails check every model output for medical advice and dosing. They are not applied to input, because real headlines mention doses and treatments, and an input filter would block real news.

**Built to be reused.** The classifier is a plain Python module with no AWS code. The model is passed in as a function, so the same module can power an MCP server or a voice briefing next.

## How it runs on AWS
```
EventBridge Scheduler (twice a day, no retries)
   -> Ingest Lambda -> 8 news sources, SEC EDGAR, NIH RePORTER, job boards
                    -> Amazon Bedrock (Nova Lite) + Bedrock Guardrails
                    -> DynamoDB (news, funding, jobs, run metadata)
Visitor -> CloudFront -> S3 (static site, Origin Access Control)
                      -> /api/* -> API Gateway HTTP API -> read-only API Lambda
```
- **One domain:** CloudFront serves the site and routes `/api/*` to API Gateway, so there is one public URL and no CORS. The API is cached for 5 minutes and throttled.
- **Lambda** on Python 3.14 and arm64 (cheapest compute). **DynamoDB** on-demand. Everything is defined in one **AWS SAM** template.
- **Cost by design:** only new items are classified, with hard caps of 100 stories and 200 jobs per run, a DynamoDB lock against overlapping runs, and a $25 AWS Budget alert. Nova Lite costs about $0.0001 per story, so a full refresh costs about a cent.

## Built with a coding agent
Claude Code (Claude Opus 5.5) built and shipped HealthSurface in one evening from a written product brief. It connected to the AWS account with `aws login` (the AWS console sign-in) and ran every AWS step itself: the identity check, the Bedrock model check, the budget, the guardrail, every `sam deploy`, the S3 uploads and the CloudFront invalidations. It tracked each build step as a Linear issue through the Linear MCP connector and deployed after every step, so there was always a working live version.

**Timeline (Oct 2, PT):** 16:42 first AWS command. 16:54 hello-world live on CloudFront. 17:16 all three tabs live with real data. 17:20 tests and the twice-daily schedule. The evening after that went to quality: a redesign, a source terms review and fixes from real use.

**What the agent caught that a tutorial would not have:**
- **A new-account quota.** The first deploy rolled back because new accounts must keep 10 Lambda concurrency units free, which the docs don't mention. The agent replaced reserved concurrency with a DynamoDB run lock.
- **Bedrock "account is being verified."** Listing models said Nova was ACTIVE, but the first real call was denied. The agent built a keyword fallback classifier so the site kept working, and items are retried with the model later. Today 165 of 169 stories and 97% of jobs are model-classified.
- **Dates from the future.** PubMed's sort date is the journal issue date, sometimes months ahead. The agent switched to the indexed date.
- **A label mismatch in the daily brief.** The model once paired a preprint's text with a "Reported news" label. The agent changed it so the model only picks stories, and each bullet reuses that story's own label and link. A test covers it.
- **Source terms.** At the owner's request the agent read every source's terms. It disabled a news feed whose terms ban automated access, deleted the stored items, and replaced it with sources whose licenses allow this use. It also added the credits that NCBI and Remote OK require.

**Proof of the agent connection:** the `proof/` folder has the identity check, the Bedrock calls before and after verification, the deploy logs and live URL checks. `PROCESS.md` has the full timeline and `FRICTION_LOG.md` lists every problem and fix.

## Quality
- 53 unit tests (taxonomy, model-reply validation, the funding fact check, Form D parsing, dedupe, paywall detection, the brief keeping each story's own label).
- All infrastructure as code. No secrets in the repo; the contact email that PubMed and SEC require is a deploy parameter.
- Every source's terms status is documented in the README, including the sources we chose not to use and why.
- Safety: guardrail on every summary, a "reading list, not medical advice" notice on every page, and a rule that blocks stories about suicide at ingest.

## Who it helps and where it is headed
**Users:** clinicians and administrators moving into health tech, founders tracking competitors and hiring, investors and analysts watching Form D filings, and anyone who wants to know whether a health headline is a study or a sales pitch.

**Next:**
- An MCP server and an Alexa+ daily voice briefing, reusing the classifier module as-is.
- ClinicalTrials.gov and Europe PMC as sources. Email digests by focus area.

**Business model:** the reading list stays free. Paid alerts for investors and operators (new Form D filings and hiring surges by sector and focus area), and paid job postings for health companies.

**Licensing before revenue:** every source is public domain, an open metadata API, or CC BY-ND with headline-and-link use (which permits commercial use), so a paid tier needs no new content licenses.
