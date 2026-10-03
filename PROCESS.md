# How the coding agent helped

Agent: Claude Code (Claude Opus 5.5), working in the terminal with the AWS CLI, SAM CLI and a Linear MCP connection for task tracking.

## Timeline (Fri Oct 2, PT)
- 16:42 Read the brief, created the Linear project with one issue per build step, installed the AWS and SAM CLIs.
- 16:46 Checked the AWS identity, listed Nova models and made a test call (blocked by account verification), created the $25 budget. Proof: `proof/00-identity-and-bedrock.txt`.
- 16:50 Wrote the SAM template (S3 + CloudFront with OAC, HTTP API + Lambda behind `/api/*` on the same domain, DynamoDB, EventBridge Scheduler disabled by default) and deployed a hello-world. Proof: `proof/01-*`.

## Key decisions
- One CloudFront domain serves both the static site and `/api/*`, so there is no CORS and only one public URL.
- Python 3.14 on arm64 Lambda (the cheapest compute, and it matches the local Python).
- The refresh schedule ships DISABLED, and it is only enabled after the cost estimate is approved.
- Classification lives in a plain Python module with no AWS handler code, so it can be reused for the Alexa+ MCP server.
- 17:00 Bedrock opened up. Created the Bedrock guardrail, wrote the Bedrock adapter (`handlers/bedrock.py`) that turns Nova Lite plus the output guardrail into a plain `invoke(system, user)` callable for `classify.py`.
- 17:05 Wrote the news fetchers (FDA RSS, openFDA drugs and devices, medRxiv, PubMed E-utilities, commercial RSS), the free-to-read checker (robots.txt, status, JSON-LD `isAccessibleForFree`, wall markers; it reads at most 150 KB of HTML and keeps no text), the ingest and API handlers, and the three-tab front end. Proof: `proof/02-news-tab.png`.
- 17:12 Reviewed the first live output, found and fixed future PubMed dates and invented funding rounds (see FRICTION_LOG).
- 17:15 Funding: SEC EDGAR Form D fetcher (full-text search by health industry group, then the filing XML for issuer, amount sold, offering size and date). News funding records go through the code-side fact check. Proof: `proof/03-funding-tab.png`.
- 17:16 Jobs: `scripts/verify_boards.py` verified Greenhouse, Lever and Ashby tokens for a 50-company seed list (35 kept after a manual name check). The ingest pulls the newest 60 per company plus health-related RemoteOK jobs, removes closed postings, and auto-verifies boards for companies in news funding announcements (Tiny Health was added this way). Proof: `proof/04-jobs-tab.png`.
- 17:20 Tests (28, pytest), the daily brief, and the twice-daily schedule enabled (`proof/05-sam-deploy-schedule-enabled.log`).
- 17:25 Ran capped backfill runs (200 jobs each) so most jobs are model-classified before judging.

## Prompts that shaped the build
- The full brief in `healths-claude-code-prompt.md` (build order, cut order, source rules).
- "Create a project called HealthSurface with one issue per build step (0 to 7)... Move each issue to In Progress when you start it and Done when it is deployed and checked." The agent tracked every step in Linear through the Linear MCP connector.
- "You can just keep it public": the repo stays public by the owner's choice, so the agent redacted the contact email from committed deploy logs.
- 17:27 Final check in a fresh browser profile (no cookies, no login): every route returns 200, all three tabs render cards, the brief shows, and the narrow layout works. Proof: `proof/07-*`. Note: headless Chrome will not render narrower than 500px, so the narrow screenshot is at 500px.
- 17:55 PT: Owner rule: never pull a story about suicide. `config.BLOCKED_STORY_TERMS` (suicide, suicides, suicidal, suicidality) is checked on the headline and feed description at ingest, so blocked stories are never classified or stored and the run report logs them as 'blocked topic'. The API also hides any stored story or brief bullet that matches, as a backstop.
- 18:10 PT: UI redesign at the owner's request: a light newsprint theme (Newsreader serif for reading, Inter for UI), a masthead with dateline, black pill section tabs, and an "In focus" band modeled on Everyday Health's video section (a featured story with an auto-advancing scrollable "Up next" list that pauses on hover and stays still under reduced motion). Story grid, funding and job rows. Removed the automatic dark mode.
- 19:55 PT: Replaced the disabled commercial feeds with sources whose terms clearly allow this use: KFF Health News (CC BY-NC-ND) and The Conversation (CC BY-ND) for Reported news, and the CMS and CDC newsrooms (public domain) for Press release. Added NIH RePORTER SBIR and STTR grants to Funding. Rejected PR Newswire (its terms ban robots and republishing). Skipped Business Wire and GlobeNewswire (terms unconfirmed). SBIR.gov returns 403.

## Proof of the coding agent connection to AWS
- Claude Code ran in the owner's terminal and connected to the AWS account with `aws login`, the AWS CLI sign-in that uses the owner's AWS Management Console credentials in the browser. Every AWS action in this build (identity check, Bedrock calls, budget, guardrail, `sam deploy`, S3 sync, CloudFront invalidation, Lambda invokes) was run by the agent through that session.
- `proof/00-identity-and-bedrock.txt`: `aws sts get-caller-identity`, the Nova model list, the first Bedrock call (blocked by account verification) and the call after it cleared, the budget and the guardrail.
- `proof/01-sam-deploy-hello-world.log` and `proof/05-sam-deploy-schedule-enabled.log`: the agent's CloudFormation deploys (contact email redacted).
- `proof/01-live-url-check.txt` and `proof/07-*`: the live URL checked from the agent's session and in a fresh browser profile.
