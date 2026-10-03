"""Bedrock adapter: turns Nova + Guardrails into the plain `invoke(system, user)` callable
that classify.py expects. Guardrails check model output only, since source headlines can
legitimately mention doses or treatments."""
import json
import os

import boto3
from botocore.config import Config

_client = boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 3, "mode": "adaptive"}, read_timeout=30))
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-micro-v1:0")
# The daily summary is written for the ear, so it uses a newer writer (about two calls a day).
SUMMARY_MODEL_ID = os.environ.get("SUMMARY_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
SUMMARY_FALLBACK_MODEL_ID = "us.amazon.nova-pro-v1:0"
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")

usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "guardrail_blocks": 0}


class GuardrailBlocked(Exception):
    pass


def _guard(text: str) -> None:
    if not GUARDRAIL_ID:
        return
    res = _client.apply_guardrail(guardrailIdentifier=GUARDRAIL_ID, guardrailVersion=GUARDRAIL_VERSION,
                                  source="OUTPUT", content=[{"text": {"text": text}}])
    if res.get("action") == "GUARDRAIL_INTERVENED":
        usage["guardrail_blocks"] += 1
        raise GuardrailBlocked()


def invoke(system: str, user: str, max_tokens: int = 400, model_id: str | None = None, temperature: float = 0) -> str:
    res = _client.converse(
        modelId=model_id or MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    usage["calls"] += 1
    usage["input_tokens"] += res["usage"]["inputTokens"]
    usage["output_tokens"] += res["usage"]["outputTokens"]
    text = res["output"]["message"]["content"][0]["text"]
    try:
        summary = json.loads(text[text.index("{"): text.rindex("}") + 1]).get("summary")
    except ValueError:
        summary = None
    _guard(summary or text)
    return text
