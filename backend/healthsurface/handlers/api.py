"""Read-only JSON API behind CloudFront at /api/*. Filtering happens in the browser."""
import json

from .. import classify, config, locations, taxonomy
from . import store


def _respond(body, status=200, max_age=300):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": f"public, max-age={max_age}"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def _sorted(rows, key="date"):
    return sorted(rows, key=lambda r: r.get(key) or "", reverse=True)


def briefing(summary: dict | None) -> list[dict]:
    """Alexa Flash Briefing feed (JSON). Alexa reads `mainText` when someone asks for the summary."""
    if not summary:
        return []
    return [{"uid": f"healthsurface-summary-{summary['date']}", "updateDate": summary["generated_at"].replace("+00:00", ".0Z"),
             "titleText": f"{config.APP_NAME} summary for {summary['day']}", "mainText": summary["spoken"],
             "redirectionUrl": config.SITE_URL,
             # With a recording, Alexa plays our Amazon Polly voice instead of reading mainText.
             **({"streamUrl": config.SITE_URL + summary["audio"]} if summary.get("audio") else {})}]


def handler(event, context):
    path = (event.get("rawPath") or "").removeprefix("/api").strip("/")
    if path == "health":
        return _respond({"ok": True}, max_age=0)
    if path == "meta":
        last = store.get_meta("last_run") or {}
        brief = store.get_meta("brief")
        if brief:
            brief["bullets"] = [b for b in brief.get("bullets", []) if not classify.is_blocked_story(b.get("title"), b.get("text"))]
        return _respond({"app": config.APP_NAME, "tagline": config.TAGLINE, "disclaimer": config.DISCLAIMER,
                         "taxonomy": taxonomy.as_dict(), "last_run": last.get("started_at"),
                         "sources": {k: {"name": v["name"], "label": v["label"]} for k, v in config.NEWS_SOURCES.items()},
                         "brief": brief, "summary": store.get_meta("summary")})
    if path == "briefing":
        return _respond(briefing(store.get_meta("summary")))
    if path == "news":
        rows = [r for r in store.scan_all(store.news) if not classify.is_blocked_story(r.get("title"), r.get("summary"))]
        return _respond({"items": _sorted(rows)[:600]})
    if path == "funding":
        return _respond({"items": _sorted(store.scan_all(store.funding))})
    if path == "jobs":
        rows = store.scan_all(store.jobs)
        for row in rows:  # derived at read time so parser fixes apply to every stored job
            row["countries"] = locations.countries_for(row.get("location"))
        return _respond({"items": _sorted(rows, "posted")})
    return _respond({"error": "not found"}, status=404)
