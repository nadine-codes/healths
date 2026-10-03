"""Scheduled ingest: fetch, dedupe, check free-to-read, classify (capped), store."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError

from .. import classify, config
from ..sources import funding as funding_src
from ..sources import grants as grants_src
from ..sources import jobs as jobs_src
from ..sources import news as news_src
from . import bedrock, store

log = logging.getLogger()
log.setLevel(logging.INFO)

STORED_NEWS_FIELDS = ("id", "url", "title", "date", "source", "source_name", "label",
                      "journal", "category", "license", "company")


def _model():
    return bedrock.invoke if bedrock.MODEL_ID else None


def ingest_news(report: dict) -> list[dict]:
    fetched, report["sources"] = news_src.fetch_all()
    existing = {r["id"]: r for r in store.scan_all(store.news, "id, classifier")}

    # Dedupe by URL hash within this batch and against the table. Stored items that only got
    # the keyword fallback are retried with the model once the new items are done.
    batch, retry, seen = [], [], set()
    for item in fetched:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        if item["id"] not in existing:
            batch.append(item)
        elif existing[item["id"]].get("classifier") == "rules":
            retry.append(item)

    skipped, kept = [], []
    for item in batch:
        if classify.is_blocked_story(item["title"], item.get("description")):
            skipped.append({"url": item["url"], "reason": "blocked topic"})
            continue
        meta = config.NEWS_SOURCES[item["source"]]
        if not meta["free_to_read"]:
            skipped.append({"url": item["url"], "reason": "source not free to read"})
            continue
        if meta.get("commercial"):
            ok, reason = news_src.free_to_read(item["url"])
            if not ok:
                skipped.append({"url": item["url"], "reason": reason})
                continue
        kept.append(item)

    kept.extend(retry)
    invoke = _model()
    rows, funding_rows, model_calls = [], [], 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for item in kept:
        use_model = invoke if model_calls < config.MAX_NEW_STORIES_PER_RUN else None
        if use_model is None and item["id"] in existing:
            continue  # retry only when model budget remains this run
        result, method = classify.classify_story(item, use_model)
        model_calls += use_model is not None
        row = {k: item[k] for k in STORED_NEWS_FIELDS if item.get(k)}
        row.update(sector=result["sector"], focus_areas=result["focus_areas"], summary=result["summary"],
                   confidence=result["confidence"], classifier=method, is_funding=result["is_funding_announcement"],
                   ingested_at=now)
        rows.append(row)
        if result.get("funding"):
            funding_rows.append(funding_from_story(row, result["funding"]))

    store.put_many(store.news, rows)
    store.put_many(store.funding, funding_rows)
    report["news"] = {"fetched": len(fetched), "new": len(batch), "stored": len(rows),
                      "retried": len(retry), "skipped": len(skipped), "model_calls": model_calls}
    report["skipped"] = skipped[:50]
    for s in skipped:
        log.info("skipped %s: %s", s["url"], s["reason"])
    return rows


def funding_from_story(story: dict, f: dict) -> dict:
    return {
        "id": f"news#{story['id']}",
        "company": f["company"],
        "amount_usd": f.get("amount_usd"),
        "round_stage": f.get("round_stage"),
        "date": f.get("date") or story["date"],
        "investors": f.get("investors") or [],
        "source_url": story["url"],
        "source_name": story["source_name"],
        "source_kind": "News story",
        "sector": story["sector"],
        "focus_areas": story["focus_areas"],
    }


def ingest_funding(report: dict) -> None:
    existing = {r["id"] for r in store.scan_all(store.funding, "id")}
    rows = funding_src.fetch_new(existing)
    try:
        grants = grants_src.fetch_new(existing)
    except Exception as err:  # noqa: BLE001 - grants are additive; Form D still lands
        log.warning("NIH RePORTER failed: %s", err)
        grants = []
    store.put_many(store.funding, rows + grants)
    report["funding"] = {"form_d_new": len(rows), "nih_grants_new": len(grants)}


JOB_FIELDS = ("id", "company", "title", "url", "location", "remote", "posted", "source", "source_name",
              "sector", "focus_areas")


def _discover_companies(report: dict) -> list[dict]:
    """Verify job boards for companies that appeared in news funding announcements."""
    state = store.get_meta("job_companies") or {"verified": [], "tried": []}
    known = {c["name"].lower() for c in jobs_src.COMPANIES + state["verified"]} | set(state["tried"])
    candidates = {r["company"]: r for r in store.scan_all(store.funding) if r.get("source_kind") == "News story"}
    added = []
    for name, rec in list(candidates.items())[:20]:
        if name.lower() in known:
            continue
        found = jobs_src.verify_company(name, rec.get("sector"), rec.get("focus_areas") or [])
        state["tried"].append(name.lower())
        if found:
            state["verified"].append(found)
            added.append(name)
    store.put_meta("job_companies", state)
    report["jobs_companies_added"] = added
    return state["verified"]


def ingest_jobs(report: dict) -> None:
    extra = _discover_companies(report)
    fetched, report["job_sources"], boards_ok = jobs_src.fetch_all(extra)
    existing = {r["id"]: r for r in store.scan_all(store.jobs, "id, classifier, job_type")}
    fetched = list({j["id"]: j for j in fetched}.values())
    new = [j for j in fetched if j["id"] not in existing]

    def needs_retry(row):  # keyword-only rows, and "Other" from the first model prompt version
        return row and (row.get("classifier") == "rules" or (row.get("classifier") == "model" and row.get("job_type") == "Other"))

    retry = [j for j in fetched if needs_retry(existing.get(j["id"]))]

    invoke = _model()
    to_model = (new + retry)[: config.MAX_NEW_JOBS_PER_RUN] if invoke else []
    model_ids = {j["id"] for j in to_model}
    with ThreadPoolExecutor(4) as pool:
        modelled = {j["id"]: res for j, res in zip(to_model, pool.map(lambda j: classify.classify_job(j, invoke), to_model))}

    rows = []
    for job in new + [j for j in retry if j["id"] in model_ids]:
        result, method = modelled.get(job["id"]) or classify.classify_job(job)
        row = {k: job[k] for k in JOB_FIELDS if job.get(k) not in (None, "")}
        row.update(result, classifier=method)
        rows.append(row)
    store.put_many(store.jobs, rows)

    # Remove postings that closed: anything stored from a board that loaded but no longer lists it.
    live = {j["id"] for j in fetched}
    closed = [i for i in existing if i not in live and any(i.startswith(p) for p in boards_ok)]
    store.delete_many(store.jobs, closed)
    report["jobs"] = {"fetched": len(fetched), "new": len(new), "stored": len(rows), "model": len(to_model),
                      "closed_removed": len(closed)}


def ingest_brief(report: dict) -> None:
    """Today's brief: one model call per day from stories already stored."""
    today = datetime.now(timezone.utc).date().isoformat()
    current = store.get_meta("brief")
    if current and current.get("date") == today:
        report["brief"] = "already built today"
        return
    invoke = _model()
    if not invoke:
        return
    recent = [s for s in sorted(store.scan_all(store.news), key=lambda s: s.get("date") or "", reverse=True)
              if s.get("classifier") == "model"][:25]
    bullets = classify.todays_brief(recent, invoke)
    store.put_meta("brief", {"date": today, "bullets": bullets})
    report["brief"] = len(bullets)


SUMMARY_TZ = ZoneInfo("America/New_York")  # the summary is dated for US morning listeners


def _spoken_money(n: float) -> str:
    for size, word in ((1e9, "billion"), (1e6, "million")):
        if n >= size:
            return f"${n / size:.1f}".removesuffix(".0") + f" {word}"
    return f"${n:,.0f}"


def summary_items(today) -> list[dict]:
    """Stories from the last three days plus the week's biggest SEC and NIH funding, newest first."""
    stories = sorted((s for s in store.scan_all(store.news) if s.get("classifier") == "model" and s.get("summary")
                      and not classify.is_blocked_story(s.get("title"), s.get("summary"))),
                     key=lambda s: s.get("date") or "", reverse=True)
    cutoff = (today - timedelta(days=3)).isoformat()
    picked = [s for s in stories if (s.get("date") or "") >= cutoff][:30]
    picked += [s for s in stories if s not in picked][: max(0, 15 - len(picked))]
    week = (today - timedelta(days=7)).isoformat()
    money = sorted((r for r in store.scan_all(store.funding) if r.get("amount_usd") and (r.get("date") or "") >= week
                    and r.get("source_kind") != "News story"),  # news funding is already in the stories
                   key=lambda r: r["amount_usd"], reverse=True)[:4]
    funding = [{"title": (f"{r['company']} was awarded a {_spoken_money(r['amount_usd'])} {r['source_kind']}"
                          if r["source_kind"].startswith("NIH") else
                          f"{r['company']} reported raising {_spoken_money(r['amount_usd'])} in an SEC Form D filing"),
                "summary": f"Project: {r['project_title']}." if r.get("project_title") else "",
                "label": r["source_kind"], "source_name": r["source_name"], "url": r["source_url"]} for r in money]
    return [{k: s.get(k) for k in ("title", "summary", "label", "source_name", "url")} for s in picked] + funding


def _summary_invoke(report: dict):
    def invoke(system: str, user: str) -> str:
        for model in (bedrock.SUMMARY_MODEL_ID, bedrock.SUMMARY_FALLBACK_MODEL_ID):
            try:
                text = bedrock.invoke(system, user, 1500, model, 0.5)
                report["summary_model"] = model
                return text
            except ClientError as err:  # e.g. model access not granted yet: try the next writer
                log.warning("summary model %s failed: %s", model, err)
        raise RuntimeError("no summary model available")
    return invoke


def ingest_summary(report: dict) -> None:
    """The daily summary: one model call (two if the first reply fails a check) each run."""
    invoke = _model()
    if not invoke:
        return
    now = datetime.now(SUMMARY_TZ)
    items = summary_items(now.date())
    summary = classify.todays_summary(items, _summary_invoke(report))
    day, dropped = f"{now:%A}, {now:%B} {now.day}", summary.pop("dropped")
    store.put_meta("summary", {**summary, "date": now.date().isoformat(), "day": day,
                               "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "spoken": classify.spoken_summary(summary, day)})
    report["summary"] = {"items": len(items), "cited": len(summary["sources"]), "dropped": dropped}


STAGES = {"news": ingest_news, "funding": ingest_funding, "jobs": ingest_jobs, "brief": ingest_brief,
          "summary": ingest_summary}


def handler(event, context):
    stages = (event or {}).get("stages") or list(STAGES)
    for key in bedrock.usage:  # warm containers keep module state; report per run
        bedrock.usage[key] = 0
    if not store.acquire_lock("ingest"):
        log.warning("another ingest run holds the lock; exiting")
        return {"ok": False, "reason": "locked"}
    started = time.time()
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        for name in stages:
            try:
                STAGES[name](report)
            except Exception as err:  # noqa: BLE001 - one failing stage must not stop the others
                log.exception("stage %s failed", name)
                report[f"{name}_error"] = str(err)[:300]
    finally:
        report["seconds"] = round(time.time() - started, 1)
        report["bedrock"] = dict(bedrock.usage)
        store.put_meta("last_run", report)
        store.release_lock("ingest")
    log.info("report %s", report)
    return report
