"""Read-only HTTP API. Placeholder until the feeds land."""
import json


def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"ok": True, "path": event.get("rawPath")}),
    }
