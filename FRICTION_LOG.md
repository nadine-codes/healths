# Friction log

- 16:42 PT: No AWS CLI or SAM CLI on the machine. Installed both with Homebrew (about 2 minutes).
- 16:46 PT: Bedrock `Converse` on Nova Micro returned AccessDenied: "Your account is currently being verified". The model list showed Nova as ACTIVE, so listing models is not proof of access. Only a real test call shows it. Built a rule-based fallback classifier so the site works while verification is pending.
- 16:50 PT: The first `sam deploy` rolled back. `ReservedConcurrentExecutions: 1` failed because new accounts have a Lambda concurrency quota of 10 and must keep 10 unreserved. The docs do not mention this new-account limit near the property. Removed it. A rule in the ingest code prevents overlapping runs instead.
- 16:50 PT: `aws login` did not set a default region, so the CloudFormation CLI calls failed with NoRegion. Fixed with `aws configure set region us-east-1`.
