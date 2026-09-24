"""Machine-readable authoritative usage summary model."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .aggregate import UsageRow, filter_events, group_events, parse_window
from .model import UsageEvent
from .project import ProjectIdentity

SCHEMA_VERSION = 1
VALID_SCOPES = ("current_project", "all_projects")
DETAIL_FIELDS = ("input_tokens", "cache_tokens", "output_tokens", "thinking_tokens")


def _sum_available(values: Iterable[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _project_dict(project: ProjectIdentity | None) -> dict[str, str] | None:
    return None if project is None else {"key": project.key, "label": project.label}


def _latest_project(events: Sequence[UsageEvent]) -> ProjectIdentity | None:
    if not events:
        return None
    event = max(events, key=lambda item: (item.completed_at, item.recorded_at, item.event_id))
    return ProjectIdentity(event.project_key, event.project_label, Path(""))


def _row_dict(row: UsageRow) -> dict[str, object]:
    return {
        "project_key": row.project_key,
        "project_label": row.project_label,
        "account_alias": row.account_alias,
        "role": row.role,
        "provider": row.provider,
        "model": row.model,
        "precision": "exact" if row.total_tokens is not None else "unavailable",
        "usage": {
            "input_tokens": row.input_tokens,
            "cache_tokens": row.cache_tokens,
            "output_tokens": row.output_tokens,
            "thinking_tokens": row.thinking_tokens,
            "total_tokens": row.total_tokens,
        },
    }


def build_summary(
    events: Iterable[UsageEvent],
    *,
    window_name: str,
    scope: str,
    accounts: Iterable[str],
    active_account: str | None,
    selected_account: str | None = None,
    now: datetime | None = None,
    project_override: ProjectIdentity | None = None,
    malformed_event_count: int = 0,
) -> dict[str, object]:
    """Build a stable summary from normalized events without persisting raw data."""
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of {VALID_SCOPES}")
    current_time = now or datetime.now(timezone.utc)
    window = parse_window(window_name)
    all_events = list(events)
    current_project = project_override or _latest_project(all_events)

    # Compute the unfiltered global total first; account/project selection must
    # never alter this authoritative five-hour aggregate.
    global_events = filter_events(all_events, now=current_time, window=window)
    global_rows = group_events(global_events)

    account_filter = selected_account if selected_account is not None else active_account
    selected_events = global_events
    if account_filter is not None:
        selected_events = [event for event in selected_events if event.account_alias == account_filter]
    if scope == "current_project":
        if current_project is None:
            selected_events = []
        else:
            selected_events = [event for event in selected_events if event.project_key == current_project.key]
    selected_rows = group_events(selected_events)

    cumulative_events = all_events
    if current_project is not None:
        cumulative_events = [event for event in cumulative_events if event.project_key == current_project.key]
        if account_filter is not None:
            cumulative_events = [event for event in cumulative_events if event.account_alias == account_filter]
    else:
        cumulative_events = []
    cumulative_rows = group_events(cumulative_events)

    known_accounts = set(accounts)
    known_accounts.update(event.account_alias for event in all_events)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": current_time.isoformat(),
        "window": window_name,
        "window_started_at": (current_time - window).isoformat(),
        "scope": scope,
        "current_project": _project_dict(current_project),
        "selected_account": selected_account,
        "accounts": sorted(known_accounts),
        "active_account": active_account,
        "all_projects_window_total": _sum_available(row.total_tokens for row in global_rows),
        "selected_scope_window_total": _sum_available(row.total_tokens for row in selected_rows),
        "current_project_cumulative_total": _sum_available(row.total_tokens for row in cumulative_rows),
        "available_detail_fields": [
            field for field in DETAIL_FIELDS
            if any(getattr(row, field) is not None for row in selected_rows)
        ],
        "rows": [_row_dict(row) for row in selected_rows],
        "diagnostics": {"malformed_event_count": malformed_event_count},
    }


__all__ = [
    "SCHEMA_VERSION",
    "VALID_SCOPES",
    "DETAIL_FIELDS",
    "build_summary",
]
