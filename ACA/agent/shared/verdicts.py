"""Shared verdict helpers for ACA runners and audits."""

from __future__ import annotations


VALID_DUAL_VERDICT_STATUSES = {"AC", "WA", "RE", "TIMEOUT", "TLE", "MLE", "OOM"}


def is_valid_dual_status(status: str | None) -> bool:
    return (status or "") in VALID_DUAL_VERDICT_STATUSES
