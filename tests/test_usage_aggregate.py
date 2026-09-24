import unittest
import re
from unittest import mock
from datetime import datetime, timedelta, timezone

from scripts.dev_orchestrator_usage.aggregate import (
    filter_events, group_events, parse_window, render_project_report, render_all_projects_report,
)
from scripts.dev_orchestrator_usage.model import EventContext, TokenUsage, UsageEvent

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)

def event_at(when=NOW, **kw):
    return UsageEvent.new(
        started_at=when, completed_at=when, project_key=kw.get("project_key", "p"), project_label=kw.get("project_label", "demo"),
        account_alias=kw.get("account", "personal"), task_id="t", thread_id=None,
        session_id="s", conversation_id=None, role=kw.get("role", "implement"),
        provider=kw.get("provider", "openai"), model=kw.get("model", "luna"),
        source="test", precision="exact", usage=TokenUsage(
            kw.get("input"), kw.get("cache"), kw.get("write"), kw.get("output"),
            kw.get("thinking"), kw.get("total")),
    )

class UsageAggregationTests(unittest.TestCase):
    def test_five_hour_window_is_open_left_closed_right(self):
        events = [event_at(NOW - timedelta(hours=5)), event_at(NOW - timedelta(hours=4, minutes=59)), event_at(NOW)]
        selected = filter_events(events, now=NOW, window=parse_window("5h"))
        self.assertEqual([e.completed_at for e in selected], [NOW - timedelta(hours=4, minutes=59), NOW])

    def test_same_project_accounts_are_separate_then_summed(self):
        rows = group_events([event_at(account="personal", total=100), event_at(account="work", total=60)])
        self.assertEqual([row.total_tokens for row in rows], [100, 60])

    def test_unavailable_is_not_rendered_as_zero(self):
        self.assertIn("N/A", render_project_report([event_at()], project_label="demo", now=NOW))

    def test_total_does_not_add_cache_and_thinking_twice(self):
        row = group_events([event_at(input=100, cache=80, output=20, thinking=10, total=120)])[0]
        self.assertEqual(row.total_tokens, 120)

    def test_all_unknown_details_hide_detail_columns_but_keep_total(self):
        report = render_project_report([event_at(total=9)], project_label="demo", now=NOW)
        header = report.splitlines()[0]
        self.assertNotIn("INPUT", header); self.assertNotIn("CACHE", header)
        self.assertNotIn("OUTPUT", header); self.assertNotIn("THINK", header)
        self.assertIn("TOTAL", header); self.assertIn("9", report)

    def test_mixed_known_details_keep_columns_and_render_na(self):
        report = render_project_report([event_at(account="a", cache=4, thinking=2, total=5), event_at(account="b", total=3)], project_label="demo", now=NOW)
        self.assertIn("CACHE", report); self.assertIn("THINK", report)
        self.assertIn("a", report); self.assertIn("b", report)
        self.assertGreaterEqual(report.count("N/A"), 2)

    def test_project_total_has_same_columns_as_header(self):
        report = render_project_report([event_at(cache=4, thinking=2, total=5)], project_label="demo", now=NOW)
        lines = report.splitlines(); self.assertEqual(lines[3].rstrip().endswith("5"), True)

    def test_all_projects_report_has_sections_and_single_total(self):
        events = [event_at(total=5), event_at(total=7, project_key="q", project_label="other")]
        report = render_all_projects_report(events, now=NOW)
        self.assertIn("demo", report); self.assertIn("other", report)
        self.assertIn("ALL PROJECTS TOTAL  12", report)

    def test_all_projects_unknown_total_is_na(self):
        self.assertIn("ALL PROJECTS TOTAL  N/A", render_all_projects_report([event_at()], now=NOW))

    def test_table_numeric_columns_have_stable_starts(self):
        report = render_project_report([event_at(account="long-account", model="m", input=999, total=1000), event_at(account="x", model="long-model", input=1, total=2)], project_label="demo", now=NOW)
        lines = report.splitlines(); header = lines[0]
        ends = [header.index("INPUT") + len("INPUT"), header.index("TOTAL") + len("TOTAL")]
        for line in lines[1:3]:
            self.assertGreaterEqual(len(line), ends[-1])

    def test_compact_rounding_does_not_emit_1000k(self):
        from scripts.dev_orchestrator_usage.aggregate import _fmt
        self.assertNotIn("1000K", _fmt(999_950))

    def test_compact_rounding_uses_half_up_at_half_tenth_boundaries(self):
        from scripts.dev_orchestrator_usage.aggregate import _fmt
        self.assertEqual(_fmt(1_249), "1.2K")
        self.assertEqual(_fmt(1_250), "1.3K")
        self.assertEqual(_fmt(1_251), "1.3K")
        self.assertEqual(_fmt(999_949), "999.9K")
        self.assertEqual(_fmt(999_950), "1M")
        self.assertEqual(_fmt(999_951), "1M")

    def test_grouping_identity_keeps_same_display_fields_with_distinct_project_keys(self):
        rows = group_events([
            event_at(project_key="project-a", project_label="Shared", total=10),
            event_at(project_key="project-b", project_label="Shared", total=20),
        ])
        self.assertEqual([row.project_key for row in rows], ["project-a", "project-b"])
        self.assertEqual([row.total_tokens for row in rows], [10, 20])

    def test_all_projects_uses_one_now_snapshot(self):
        with mock.patch("scripts.dev_orchestrator_usage.aggregate.datetime") as dt:
            dt.now.return_value = NOW; dt.side_effect = datetime
            render_all_projects_report([event_at()], window=parse_window("5h"))
            self.assertEqual(dt.now.call_count, 1)
