from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .model import UsageEvent

@dataclass(frozen=True)
class UsageRow:
    project_key: str; project_label: str; account_alias: str; role: str; provider: str; model: str
    input_tokens: int | None; cache_tokens: int | None; output_tokens: int | None; thinking_tokens: int | None; total_tokens: int | None

def parse_window(value: str) -> timedelta:
    m = re.fullmatch(r"([1-9][0-9]*)([mhd])", value.strip().lower())
    if not m: raise ValueError("window must be a positive integer followed by m, h, or d")
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(**{"m": {"minutes": n}, "h": {"hours": n}, "d": {"days": n}}[unit])

def filter_events(events: Iterable[UsageEvent], *, now: datetime | None = None, window: timedelta | None = None,
                  project_key: str | None = None, project_label: str | None = None,
                  account_alias: str | None = None) -> list[UsageEvent]:
    now = now or datetime.now(timezone.utc); window = window or parse_window("5h")
    start = now - window
    return [e for e in events if start < e.completed_at <= now and
            (project_key is None or e.project_key == project_key) and
            (project_label is None or e.project_label == project_label) and
            (account_alias is None or e.account_alias == account_alias)]

def group_events(events: Iterable[UsageEvent]) -> list[UsageRow]:
    buckets = {}
    fields = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "thinking_tokens", "total_tokens")
    for e in events:
        key = (e.project_key, e.project_label, e.account_alias, e.role, e.provider, e.model)
        if key not in buckets: buckets[key] = {f: [] for f in fields}
        for f in fields:
            v = getattr(e.usage, f)
            if v is not None: buckets[key][f].append(v)
    rows = []
    for key, vals in buckets.items():
        cache = vals["cache_read_tokens"] + vals["cache_write_tokens"]
        rows.append(UsageRow(*key, sum(vals["input_tokens"]) if vals["input_tokens"] else None,
                             sum(cache) if cache else None,
                             sum(vals["output_tokens"]) if vals["output_tokens"] else None,
                             sum(vals["thinking_tokens"]) if vals["thinking_tokens"] else None,
                             sum(vals["total_tokens"]) if vals["total_tokens"] else None))
    return sorted(rows, key=lambda r: (r.project_label, r.account_alias, r.role, r.provider, r.model, r.project_key))

def _fmt(value):
    if value is None: return "N/A"
    if value < 1000: return str(value)
    for div, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= div:
            scaled = value / div
            if suffix == "K" and scaled >= 999.95:
                return "1M"
            return f"{scaled:.1f}{suffix}".replace(".0", "")

def render_project_report(events: Iterable[UsageEvent], *, project_label: str | None = None,
                          project_key: str | None = None, now: datetime | None = None, window: timedelta | None = None) -> str:
    rows = group_events(filter_events(events, now=now, window=window, project_label=None if project_key else project_label, project_key=project_key))
    label = project_label or (rows[0].project_label if rows else "PROJECT")
    visible = [f for f in ("input_tokens", "cache_tokens", "output_tokens", "thinking_tokens") if any(getattr(r, f) is not None for r in rows)]
    headers = ["ACCOUNT", "ROLE", "MODEL"] + [dict(input_tokens="INPUT", cache_tokens="CACHE", output_tokens="OUTPUT", thinking_tokens="THINK")[f] for f in visible] + ["TOTAL"]
    cells = [[r.account_alias, r.role, r.model] + [_fmt(getattr(r, f)) for f in visible] + [_fmt(r.total_tokens)] for r in rows]
    totals = {f: sum(getattr(r, f) for r in rows if getattr(r, f) is not None) if any(getattr(r, f) is not None for r in rows) else None for f in visible + ["total_tokens"]}
    total_cells = ["PROJECT TOTAL", "", ""] + [_fmt(totals[f]) for f in visible] + [_fmt(totals["total_tokens"])]
    all_cells = [headers] + cells + [total_cells]
    widths = [max(len(row[i]) for row in all_cells) for i in range(len(headers))]
    numeric = set(range(3, len(headers)))
    def render(row):
        return "  ".join((row[i].rjust(widths[i]) if i in numeric else row[i].ljust(widths[i])) for i in range(len(headers))).rstrip()
    lines = [render(headers)] + [render(row) for row in cells]
    lines.append("-" * len(render(headers)))
    lines.append(render(total_cells))
    lines.append("\nNote: CACHE may be part of INPUT; THINK may be part of OUTPUT. TOTAL is provider-reported.")
    return "\n".join(lines)

def render_all_projects_report(events: Iterable[UsageEvent], *, now=None, window=None) -> str:
    now = now or datetime.now(timezone.utc)
    window = window or parse_window("5h")
    selected = filter_events(events, now=now, window=window)
    labels = sorted({e.project_label for e in selected})
    sections = [f"PROJECT: {l}\n" + render_project_report(selected, project_label=l, now=now, window=window) for l in labels]
    rows = group_events(selected)
    total = sum(r.total_tokens for r in rows if r.total_tokens is not None)
    return "\n\n".join(sections + [f"ALL PROJECTS TOTAL  {_fmt(total) if any(r.total_tokens is not None for r in rows) else 'N/A'}"])
