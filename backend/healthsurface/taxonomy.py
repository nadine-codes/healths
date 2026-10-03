"""Shared taxonomy loaded from taxonomy.json (also served to the front end)."""
import json
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "taxonomy.json").read_text())

SECTORS: list[str] = _DATA["sectors"]
FOCUS_AREAS: list[str] = _DATA["focus_areas"]
EVIDENCE_LABELS: dict[str, str] = _DATA["evidence_labels"]
ROUND_STAGES: list[str] = _DATA["round_stages"]
FUNCTION_GROUPS: dict[str, list[str]] = _DATA["function_groups"]
JOB_TYPES: list[str] = [t for types in FUNCTION_GROUPS.values() for t in types] + ["Other"]
EMPLOYMENT_TYPES: list[str] = _DATA["employment_types"]
SENIORITY: list[str] = _DATA["seniority"]


def as_dict() -> dict:
    return _DATA


def function_group_for(job_type: str) -> str:
    for group, types in FUNCTION_GROUPS.items():
        if job_type in types:
            return group
    return "Other"
