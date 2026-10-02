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
