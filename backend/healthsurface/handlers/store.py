"""DynamoDB access. Tables are small (hundreds to a few thousand rows), so scans are fine."""
import os
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

_ddb = boto3.resource("dynamodb")
news = _ddb.Table(os.environ.get("NEWS_TABLE", "news"))
funding = _ddb.Table(os.environ.get("FUNDING_TABLE", "funding"))
jobs = _ddb.Table(os.environ.get("JOBS_TABLE", "jobs"))
meta = _ddb.Table(os.environ.get("META_TABLE", "meta"))


def to_ddb(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_ddb(v) for k, v in value.items() if v is not None and v != ""}
    if isinstance(value, list):
        return [to_ddb(v) for v in value]
    return value


def from_ddb(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_ddb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_ddb(v) for v in value]
    return value


def scan_all(table, projection: str | None = None) -> list[dict]:
    kwargs = {"ProjectionExpression": projection} if projection else {}
    items, start = [], None
    while True:
        if start:
            kwargs["ExclusiveStartKey"] = start
        page = table.scan(**kwargs)
        items.extend(page.get("Items", []))
        start = page.get("LastEvaluatedKey")
        if not start:
            return [from_ddb(i) for i in items]


def put_many(table, rows: list[dict]) -> None:
    with table.batch_writer(overwrite_by_pkeys=["id"]) as batch:
        for row in rows:
            batch.put_item(Item=to_ddb(row))


def delete_many(table, ids: list[str]) -> None:
    with table.batch_writer() as batch:
        for i in ids:
            batch.delete_item(Key={"id": i})


def acquire_lock(name: str, ttl_seconds: int = 900) -> bool:
    """Prevent overlapping ingest runs (the schedule must never loop or stack up)."""
    now = int(time.time())
    try:
        meta.put_item(Item={"id": f"lock#{name}", "expires": now + ttl_seconds},
                      ConditionExpression=Attr("id").not_exists() | Attr("expires").lt(now))
        return True
    except _ddb.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def release_lock(name: str) -> None:
    meta.delete_item(Key={"id": f"lock#{name}"})


def put_meta(key: str, value: dict) -> None:
    meta.put_item(Item=to_ddb({"id": key, **value}))


def get_meta(key: str) -> dict | None:
    item = meta.get_item(Key={"id": key}).get("Item")
    return from_ddb(item) if item else None
