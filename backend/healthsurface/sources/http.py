"""Tiny stdlib HTTP helpers shared by all fetchers."""
import gzip
import json
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from functools import lru_cache

from .. import config


def get(url: str, *, timeout: int = 20, max_bytes: int | None = None, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes) if max_bytes else resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" and not max_bytes:
                body = gzip.decompress(body)
            return resp.status, body
    except urllib.error.HTTPError as err:
        return err.code, b""


def get_json(url: str, **kw):
    status, body = get(url, **kw)
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    return json.loads(body)


@lru_cache(maxsize=64)
def _robots(origin: str) -> urllib.robotparser.RobotFileParser | None:
    status, body = get(f"{origin}/robots.txt", timeout=10)
    if status != 200:
        return None
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(body.decode("utf-8", "replace").splitlines())
    return rp


def robots_allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    rp = _robots(f"{parts.scheme}://{parts.netloc}")
    return True if rp is None else rp.can_fetch(config.USER_AGENT, url)


class RateLimiter:
    def __init__(self, per_second: float):
        self.min_gap = 1.0 / per_second
        self.last = 0.0

    def wait(self):
        gap = time.monotonic() - self.last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self.last = time.monotonic()
