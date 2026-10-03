"""POST /api/ask. Limits are checked before any Bedrock call. The question is never logged or stored:
logs carry the outcome state only, and the cache key is a hash."""
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

from .. import ask
from . import bedrock, store

log = logging.getLogger()
log.setLevel(logging.INFO)

ASK_MODEL_ID = os.environ.get("ASK_MODEL_ID", "amazon.nova-lite-v1:0")  # in-region model: requests stay in us-east-1
_ddb = boto3.resource("dynamodb")
limits = _ddb.Table(os.environ.get("ASK_TABLE", "ask"))
_cache = {"docs": None, "docs_at": 0.0, "enabled": None, "enabled_at": 0.0, "salt": None}


def _respond(body: dict, status: int = 200) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps(body, separators=(",", ":"))}


def enabled() -> bool:
    """Kill switch: the meta item `ask_settings` (no deploy needed), else the ASK_ENABLED env value."""
    if time.time() - _cache["enabled_at"] > 30:
        setting = (store.get_meta("ask_settings") or {}).get("enabled")
        _cache["enabled"] = setting if setting is not None else os.environ.get("ASK_ENABLED", "false") == "true"
        _cache["enabled_at"] = time.time()
    return bool(_cache["enabled"])


def _salt() -> str:
    if not _cache["salt"]:
        item = store.get_meta("ask_salt")
        if not item:
            item = {"value": secrets.token_hex(16)}
            store.put_meta("ask_salt", item)
        _cache["salt"] = item["value"]
    return _cache["salt"]


def incr(key: str, limit: int, ttl: int):
    """Atomic counter that refuses past `limit`. Returns the new count, or None when the limit is reached."""
    try:
        res = limits.update_item(Key={"id": key}, UpdateExpression="ADD n :one SET expires = if_not_exists(expires, :exp)",
                                 ConditionExpression=Attr("n").not_exists() | Attr("n").lt(limit),
                                 ExpressionAttributeValues={":one": 1, ":exp": int(time.time()) + ttl},
                                 ReturnValues="UPDATED_NEW")
        return int(res["Attributes"]["n"])
    except limits.meta.client.exceptions.ConditionalCheckFailedException:
        return None


def _docs() -> list[dict]:
    if not _cache["docs"] or time.time() - _cache["docs_at"] > 600:
        _cache["docs"] = ask.documents(store.scan_all(store.news), store.scan_all(store.funding), store.scan_all(store.jobs))
        _cache["docs_at"] = time.time()
    return _cache["docs"]


def _guard_input(question: str) -> bool:
    """Ask guardrail on the question: denied advice topics, prompt attacks and personal details."""
    if not bedrock.GUARDRAIL_ID:
        return True
    res = bedrock._client.apply_guardrail(guardrailIdentifier=bedrock.GUARDRAIL_ID, guardrailVersion=bedrock.GUARDRAIL_VERSION,
                                          source="INPUT", content=[{"text": {"text": question}}])
    return res.get("action") != "GUARDRAIL_INTERVENED"


def _ip(event: dict) -> str:
    forwarded = (event.get("headers") or {}).get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or event.get("requestContext", {}).get("http", {}).get("sourceIp", "")


def handler(event, context):
    if not enabled():
        return _respond({"state": "off", "answer": "Ask is turned off right now.", "sources": []}, 503)
    try:
        question = json.loads(event.get("body") or "{}").get("question")
    except (ValueError, AttributeError):
        question = None
    problem = ask.validate_question(question)
    if problem:
        return _respond({"state": "invalid", "answer": problem, "sources": []}, 400)

    now = datetime.now(timezone.utc)
    day, minute = now.strftime("%Y%m%d"), now.strftime("%Y%m%d%H%M")
    state, remaining = ask.check_visitor(incr, ask.visitor_key(_ip(event), _salt(), day), day, minute)
    if state:
        log.info("ask state=%s", state)
        text = "Ask is resting until tomorrow." if state == "resting" else "You've reached today's question limit."
        return _respond({"state": state, "answer": text, "sources": [], "remaining": 0}, 429)

    try:
        docs = _docs()
        # Advice and personal questions get the refusal with cited items and no model call.
        result = ask.answer(question, docs, invoke=None) if ask.ADVICE_RE.search(question) or ask.PERSONAL_RE.search(question) \
            else None
        cache_key = f"c#{ask.question_key(question)}"
        if result is None:
            cached = limits.get_item(Key={"id": cache_key}).get("Item")
            if cached:
                result = json.loads(cached["answer"])
        if result is None:
            if not ask.retrieve(docs, question):
                result = {"state": "nothing", "answer": ask.NOTHING, "sources": []}
            elif not ask.take_answer_slot(incr, day):
                result = {"state": "resting", "answer": "Ask is resting until tomorrow.", "sources": []}
            elif not _guard_input(question):
                result = ask.refusal(ask.pivot_items(docs, question))
            else:
                result = ask.answer(question, docs, lambda s, u: bedrock.invoke(s, u, 300, ASK_MODEL_ID))
                if result["state"] in ("answer", "nothing"):
                    limits.put_item(Item={"id": cache_key, "answer": json.dumps(result),
                                          "expires": int(time.time()) + 86400})
    except bedrock.GuardrailBlocked:
        result = ask.refusal([])
    except Exception as err:  # noqa: BLE001 - log the error type only, never the question
        log.error("ask error type=%s", type(err).__name__)
        return _respond({"state": "error", "answer": "Something went wrong. Please try again in a minute.", "sources": []}, 500)
    log.info("ask state=%s", result["state"])
    return _respond({**result, "remaining": remaining})
