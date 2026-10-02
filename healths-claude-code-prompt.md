Build a web app for the AWS "Zero to Shipped" hackathon. App name: "HealthSurface" (keep the name in ONE config constant so it is easy to change). Tagline idea: "Health news, funding and jobs, labeled by source type."

DEADLINE
Fri Oct 2, 11:59 PM PT. The app must be LIVE on AWS at a public URL, reachable without a login, and stay up through at least Oct 23.
If scope is at risk, cut features from the bottom of the CUT ORDER below. Never cut the deploy. Always keep a working deployed version.

WHAT IT IS
A health news feed that labels every story by evidence level, so people can tell hype from science. It has three tabs that share the same Sector and Focus area tags:
1. News: stories with an evidence label.
2. Funding: which health companies recently raised money.
3. Jobs: open roles at those companies, filterable by function and job type.
Audience: people moving from healthcare into health tech (clinicians, administrators, non-engineers), health founders, operators, investors and analysts, and anyone who wants to tell hype from science.
It is a read-only reading list. No login, no accounts, no chat, no personal health data. Show this line on screen under the header: "This is a reading list, not medical advice." Judges and visitors open the URL and see content immediately.

NON-NEGOTIABLE RULES
- Live on AWS at a public URL by Friday afternoon PT.
- No personal health data, no user accounts, no medical advice or dosing info.
- Store only: headline, source name, link, date, tags, evidence label, and a short summary in our own words. Never republish article text. Every item links to its original source.
- Do not scrape job boards or marketplaces. Do not copy another site's funding tracker.
- Keep the GitHub repo PRIVATE until I say the Builder Center submission is done. Include an MIT LICENSE, a README with setup and run steps, and a .gitignore. No secrets in the repo.
- Keep FRICTION_LOG.md as we go: what broke, what the docs missed, what worked well.
- Keep PROCESS.md noting how you (the coding agent) helped: decisions, prompts, fixes, timeline.
- Save screenshots or logs showing you connected to my AWS account (for example the identity check and the deploy output) in a /proof folder. The hackathon requires documented proof of the coding agent connection to the AWS console.
- No em-dashes in any user-facing copy.

TAXONOMY (use these exact lists; store them in one shared JSON/TS file)
Sector (10, one per story or company):
Health Tech, Med Tech, Life Sciences and Biotech, Pharma, Supplements and Nutraceuticals, Peptides, Health AI, Health Data and IT, Care Delivery and Payers, Policy and Regulation.

Focus area (20, one or more per story or company):
Longevity and healthspan, Hormones, Sleep, Fitness and recovery, Women's health, Men's health, Metabolic health and obesity, Diabetes, Nutrition and gut health, Mental health, Neurology and brain health, Cardiovascular, Cancer and oncology, Immunology and autoimmune, Infectious disease, Skin and dermatology, Pain and chronic conditions, Genetics and precision medicine, Pediatrics and family health, Senior care.

Evidence label (News only, exactly one per story). In the UI call this field "Source type":
Press release, Preprint, Peer-reviewed study, Regulatory action, Reported news (use when none of the others fit).
The label says WHAT KIND of source it is, not how good it is. Never use wording like "high-quality evidence" or "proven" in the UI or summaries. Add a one-line tooltip per label explaining what it means (for example, a Preprint has not been peer reviewed yet).

CODE VERSUS AI
- Code decides: the evidence label (from which source the item came from), the link, the date, dedupe, the company-to-job-board match, free-to-read checks.
- AI (Bedrock) decides: Sector, Focus area, the own-words summary, and whether a headline is a funding announcement ("raised", "closes round") plus the facts stated in it.
- No paid news or funding API tonight.

Tags live on the company. Funding rounds and jobs inherit the company's Sector and Focus area. News stories are tagged one by one.

BEDROCK CLASSIFIER (strict JSON, validate against the lists above, reject anything else)
Story: { sector, focus_areas[], evidence_label, summary (max 2 sentences, our own words), confidence, is_funding_announcement }.
If is_funding_announcement is true, also extract: { company, amount, round_stage, date, investors[] } and ONLY from facts stated in the story. Leave a field null if unknown. Never guess an amount.
Job: { function_group, job_type, employment_type, seniority } from the title and posting text.
Add a short system prompt and Bedrock Guardrails. Never give medical advice in a summary.

STACK (pick the simplest option if something is easier)
- Region us-east-1
- Infrastructure as code (AWS SAM or CDK)
- Lambda + API Gateway
- DynamoDB (one table per record type is fine)
- Amazon Bedrock with Guardrails. Use an Amazon Nova model (Micro or Lite) for all Bedrock calls, so usage is covered by my AWS Free Tier credits. Only use a Claude model if I say so. Check which models I have access to first, and tell me if Nova is not enabled in us-east-1.
- Static front end (plain HTML/JS or small React) on S3 + CloudFront, with three tabs: News, Funding, Jobs
- EventBridge schedule to refresh. 2 runs a day is enough.

COST GUARDRAILS (I have $100 in AWS Free Tier credits; stay inside them. Covered services include Bedrock, Lambda, API Gateway, DynamoDB, S3, CloudFront, CloudFormation, CloudWatch and Route 53. Do not use a service that is not on that list without asking me.)
- Create an AWS Budget alert at $25 first.
- Classify only NEW items. Dedupe by URL or job id.
- Hard cap of 100 new stories and 200 new jobs classified per run.
- Never loop the schedule. Tell me the estimated cost before the first full run.

BUILD ORDER (deploy after every step so there is always a live version)
0. Check my AWS credentials and Bedrock model access. Tell me exactly what I need to enable.
1. Show a short plan, then deploy a hello-world to a public URL before building features.
2. NEWS: pull from the SOURCES list below, in priority order (open and government sources first). Fetch, dedupe, classify, summarize, store. Feed page with filters for Sector, Focus area, Evidence label. Build these first and deploy: FDA press announcements and openFDA drug approvals, the medRxiv API, PubMed E-utilities. Then add one or two commercial RSS feeds.

SOURCES (what we pull, and how we may use it)
Open and government sources (safe to reuse):
- FDA press announcements: https://www.fda.gov/news-events/fda-newsroom/press-announcements -> label Regulatory action
- openFDA API (https://open.fda.gov, CC0): drug approvals, device clearances (510(k), De Novo), recalls and enforcement, warning letters -> label Regulatory action. Device clearances also reveal new health tech, medtech and AI companies.
- NIH news releases: https://www.nih.gov/news-events/news-releases -> label Press release
- ClinicalTrials.gov API (https://clinicaltrials.gov/data-api/api): new and completed trials -> label Reported news or Preprint as fits (decide, document it)
- PubMed E-utilities (max 3 requests per second, send tool and email params). Use title, journal, date, link, and our own summary. Do NOT store abstract text (publishers may hold copyright). -> label Peer-reviewed study
- medRxiv and bioRxiv API (https://api.biorxiv.org/). Store title, link, date, category, license field, and our own summary. -> label Preprint
- Europe PMC and OpenAlex APIs if time allows (research metadata)
- NIH Office of Dietary Supplements fact sheets (https://ods.od.nih.gov) as context for supplement stories
- SEC EDGAR Form D filings (free, max 10 requests per second, MUST send an identifying User-Agent header): new fundraising by health companies. See FUNDING.
- NIH RePORTER and SBIR.gov APIs: grants and small business awards (new companies, grant funding)
FREE-TO-READ RULE: only link to articles a visitor can actually read without paying or signing up. Never link to paywalled content.
- Do NOT use STAT or Endpoints (paywalled or mostly paywalled).
- For PubMed items, link to the PubMed page, or to the PubMed Central or Europe PMC open-access copy when one exists.
- Keep a per-source "free_to_read" setting in the config file.
- Before storing a commercial link, make a light metadata-only check of that URL: HTTP status, and the isAccessibleForFree value in the page's JSON-LD markup if present. Skip the item if the status is 401, 402, or 403, or if isAccessibleForFree is false, or if the page clearly shows a subscribe wall. Do not read or store article text. Respect robots.txt. Log skipped items and the reason.
Commercial outlets (headline and link only):
- Fierce Healthcare, Fierce Biotech, MedCity News, BioPharma Dive, MobiHealthNews, Healthcare Dive, Medical News Today -> label Reported news. Verify each is free to read before keeping it.
- Use ONLY the title, link, date, and the short description in the feed. Do NOT fetch the full article page. Write our own summary. Check each site's terms and robots.txt, and drop any that prohibit this use. Log the terms status of every source in README under "Sources".
Not used: Crunchbase, TrueUp, LinkedIn, Upwork, paywalled content.
NOT TONIGHT (do not build): chatbot, height/weight or any personal profile, adverse-event "safety signal" badge, user accounts, Alexa voice.
3. FUNDING: two inputs. (a) SEC EDGAR Form D filings from health companies: amount, date, and company, which the filing shows. Form D usually does not name the round or investors, so leave those null unless a press release or news story states them. (b) Stories from the News pipeline flagged as funding announcements. Both become funding records: company, amount, round stage (Pre-seed, Seed, Series A, B, C or later, Growth, IPO, Acquisition, Grant), date, investors, source link, plus the company's tags. Funding tab lists them newest first with filters for Sector, Focus area, round stage, and amount. Every row links to the source story.
4. JOBS: build a hand-made seed list of 20 to 30 well-known health companies and verify each one's Greenhouse, Lever, or Ashby board token by actually requesting the public board endpoint (keep only tokens that return jobs; save them in a config file). Also add companies from the Funding list when their board token can be found and verified the same way. Show a company's jobs only when its token is verified. If a source returns nothing, the tab shows an honest "nothing to show yet" message. Never fake or invent jobs. Also pull the RemoteOK public feed (remoteok.com/api), crediting RemoteOK and linking each original posting. Jobs inherit the company's Sector and Focus area. Fields: company, title, function group, job type, employment type (Full-time, Part-time, Contract, Freelance, Internship), location, remote or on-site, seniority, apply link, date posted. Filters: Function group, Job type, Employment type, Sector, Focus area, remote or on-site.
   Function groups: Design, Engineering, Product, Marketing and Content, Sales and Customer, Clinical and Health, Operations and Business. Job types (about 35) include: UX/UI Product Designer, Brand Designer, Graphic Designer, Marketing Designer, UX Researcher, Software Engineer, UI Engineer, AI Engineer, Data and Analytics, DevOps and Security, QA and Test, Product Manager, Project or Program Manager, Growth and Lifecycle Marketing, Product Marketing, Content and Editorial, Social Media and Community, PR and Communications, Sales, Account Manager, Customer Success Manager, Implementation and Onboarding, Customer Support, Partnerships and Business Development, Solutions and Sales Engineering, Clinical Product Specialist, Clinical Operations, Medical Affairs and Science, Medical Writing and Content, Regulatory and Quality, Health Informatics, Operations and Strategy, Finance and Accounting, People and Recruiting, Legal and Compliance, Executive and Admin. A role that fits none is tagged Other.
   Also add a small "Contract and freelance sources" section on the Jobs tab with link-outs only (no copied listings): Magnit (magnitglobal.com), Blink UX, Aquent, Creative Circle, Robert Half Creative Group, Toptal, Braintrust, Contra, Medix, KForce, Experis.
4b. TODAY'S BRIEF (only if time allows, after all three tabs work): a short block at the top of the News tab with 5 to 7 bullets covering the day's top stories. Generate it once a day with one Bedrock call from the stories already stored (their summaries, labels, and links), written in our own words, no medical advice. Each bullet shows its evidence label and links to the story. Store it so the page does not call Bedrock on load. Keep this in the same classification and summarizing module, because the Alexa+ voice briefing will reuse it later.
5. Keep classification logic in its own module with no AWS handler code inside it. After the hackathon it gets reused in an MCP server for an Alexa+ skill. Do not build the MCP server or voice briefing now.
6. Add a few basic tests, a clean README, and the infrastructure as code. Implementation quality is scored.
7. Before the final deploy, show me the live URL, test it in a fresh browser session with no login, and tell me what to paste into the Builder Center project.

CUT ORDER (if time runs short, cut in this order, top first)
0. Today's brief (build it last, cut it first)
1. Focus area filter
2. RemoteOK feed and the Employment type filter
3. Funding amount and round filters
4. Jobs beyond the Greenhouse, Lever and Ashby feeds
Keep all three tabs live. Never cut: the deploy, News, evidence labels, source links, tests, the /proof folder.

BUILDER CENTER SUBMISSION (I will do this, help me draft the text)
Tags: #commercial-potential and #startups. The project must include: proof of the agent connection, a description and development process, the category and track, and the live URL. I can edit it until the close, so create it early and fill it in as we go.
