"""Validate operator confirmation against one rendered storage plan."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from installer.planning.storage import plan_hash_matches


def create_authorization_record(
    plan: dict[str, Any], confirmed_sha256: str, confirmed_serial: str
) -> dict[str, Any]:
    if not plan.get("read_only_plan") or not plan.get("requires_explicit_authorization"):
        raise ValueError("document is not an authorizable storage plan")
    if not plan_hash_matches(plan):
        raise ValueError("storage plan content does not match its hash")
    if confirmed_sha256 != plan.get("sha256"):
        raise ValueError("typed plan hash does not match the reviewed plan")
    if confirmed_serial != plan.get("target", {}).get("serial"):
        raise ValueError("typed serial does not match the planned system disk")
    return {
        "schema_version": 1,
        "plan_sha256": plan["sha256"],
        "target": plan["target"],
        "authorized_operation": "partition-and-format-system-disk",
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "single_disk_scope": True,
    }
