# Breach response plan (Ask chat and the rest of HealthSurface)

HealthSurface stores no accounts and no question text. The Ask table holds only hashed rate-limit counters and cached answers, and expires them within two days. This plan covers the unlikely case that something personal is exposed anyway (for example, question text found in a log by mistake, or a leaked AWS credential).

## Who
- Owner: the HealthSurface maintainer (repo owner on GitHub). They decide and send every notice.

## First hour
1. Turn Ask off without a deploy: `aws dynamodb put-item --table-name <MetaTable> --item '{"id":{"S":"ask_settings"},"enabled":{"BOOL":false}}'`.
2. Rotate any exposed AWS credential and review CloudTrail for its use.
3. Delete the exposed data (log group, table item or object). Note what it was, when and where.

## Within 24 hours
4. Work out what was exposed, for how long and to whom. Write it down in a private incident note.
5. Fix the cause and add a test or check so it can't recur.

## Notice
6. If personal health information about identifiable people was exposed, notify the people affected and post a notice on the site without unreasonable delay and within 60 days, as the FTC Health Breach Notification Rule requires; also notify the FTC when that rule applies. Check state laws (for example Washington's My Health My Data Act) for shorter deadlines. Get legal advice first; a legal review has not happened yet.
7. Post a short public summary on the site and in the repo once fixed.
