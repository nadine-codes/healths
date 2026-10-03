"""Records the daily summary with an Amazon Polly voice and saves the MP3 next to the site, so the
Listen button and voice assistants play a natural voice instead of a browser's built-in one."""
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()

VOICE = os.environ.get("SUMMARY_VOICE", "Danielle")  # a warm, conversational US English generative voice
SITE_BUCKET = os.environ.get("SITE_BUCKET", "")
MAX_CHARS = 2900  # Polly's limit per request is 3,000 characters

_polly = boto3.client("polly")
_s3 = boto3.client("s3")


def chunks(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split on sentence ends so no request runs past Polly's limit."""
    out, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and len(current) + len(sentence) + 1 > limit:
            out.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    return out + [current] if current else out


def synthesize(text: str) -> bytes:
    """MP3 from the most natural engine available: generative, then neural."""
    for engine in ("generative", "neural"):
        try:
            return b"".join(_polly.synthesize_speech(Engine=engine, VoiceId=VOICE, OutputFormat="mp3", Text=part)
                            ["AudioStream"].read() for part in chunks(text))
        except ClientError as err:
            log.warning("polly %s engine failed: %s", engine, err)
    raise RuntimeError("no Polly engine available")


def record(text: str, key: str) -> str:
    """Saves the recording under audio/ in the site bucket and returns its path on the site."""
    _s3.put_object(Bucket=SITE_BUCKET, Key=key, Body=synthesize(text), ContentType="audio/mpeg",
                   CacheControl="public, max-age=31536000, immutable")  # each summary gets a new file name
    return "/" + key
