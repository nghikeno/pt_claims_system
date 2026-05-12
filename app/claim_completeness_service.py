from __future__ import annotations

from typing import Any

import pandas as pd

from app.session_generator import generate_monthly_sessions
from app_docxtpl.context_builders import build_claim_context


def _normalise_pair(course_code: Any, group_name: Any) -> tuple[str, str]:
    return (str(course_code or "").strip().upper(), str(group_name or "").strip())


def _pairs_from_sessions(sessions_df: pd.DataFrame) -> set[tuple[str, str]]:
    if sessions_df.empty or not {"course_code", "group_name"}.issubset(sessions_df.columns):
        return set()
    return {
        _normalise_pair(row["course_code"], row["group_name"])
        for row in sessions_df[["course_code", "group_name"]].drop_duplicates().to_dict("records")
    }


def _pairs_from_claim_context(claim_context: dict[str, Any]) -> set[tuple[str, str]]:
    rows = claim_context.get("claim_rows") or []
    return {
        _normalise_pair(row.get("course_code"), row.get("group_name"))
        for row in rows
        if row.get("course_code") and row.get("group_name")
    }


def _pair_records(pairs: set[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"course_code": course_code, "group_name": group_name} for course_code, group_name in sorted(pairs)]


def _totals_by(sessions_df: pd.DataFrame, keys: list[str]) -> list[dict[str, Any]]:
    if sessions_df.empty:
        return []
    grouped = (
        sessions_df.groupby(keys, dropna=False)
        .agg(sessions=("session_date", "count"), hours=("hours", "sum"), amount=("amount", "sum"))
        .reset_index()
        .sort_values(keys)
    )
    grouped["hours"] = grouped["hours"].astype(float).round(2)
    grouped["amount"] = grouped["amount"].astype(float).round(2)
    return grouped.to_dict("records")


def audit_claim_completeness_from_data(sessions_df: pd.DataFrame, claim_context: dict[str, Any]) -> dict[str, Any]:
    expected_pairs = _pairs_from_sessions(sessions_df)
    claim_pairs = _pairs_from_claim_context(claim_context)
    missing_pairs = expected_pairs - claim_pairs
    extra_pairs = claim_pairs - expected_pairs
    return {
        "status": "PASS" if not missing_pairs and not extra_pairs else "WARN",
        "expected_pairs": _pair_records(expected_pairs),
        "claim_pairs": _pair_records(claim_pairs),
        "missing_pairs": _pair_records(missing_pairs),
        "extra_pairs": _pair_records(extra_pairs),
        "totals_by_course": _totals_by(sessions_df, ["course_code"]),
        "totals_by_group": _totals_by(sessions_df, ["course_code", "group_name"]),
    }


def build_claim_completeness_audit(lecturer_id: int, year: int, month: int) -> dict[str, Any]:
    sessions_df = generate_monthly_sessions(lecturer_id, year, month)
    claim_context = build_claim_context(sessions_df, year, month)
    return audit_claim_completeness_from_data(sessions_df, claim_context)
