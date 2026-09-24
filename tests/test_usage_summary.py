import unittest
from datetime import datetime, timedelta, timezone

from scripts.dev_orchestrator_usage.model import TokenUsage, UsageEvent
from scripts.dev_orchestrator_usage.summary import build_summary


NOW = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)


def event_at(when=NOW, *, project_key="old", project_label="Old", account="personal", total=None,
             input_tokens=None, output_tokens=None):
    return UsageEvent.new(
        started_at=when,
        completed_at=when,
        project_key=project_key,
        project_label=project_label,
        account_alias=account,
        task_id=f"task-{project_key}-{account}-{when.isoformat()}",
        thread_id=None,
        session_id="session",
        conversation_id=None,
        role="implement",
        provider="openai",
        model="luna",
        source="test",
        precision="exact",
        usage=TokenUsage(input_tokens, None, None, output_tokens, None, total),
    )


EVENTS = [
    event_at(NOW - timedelta(hours=4), project_key="old", project_label="Old", account="personal", total=100),
    event_at(NOW - timedelta(hours=4), project_key="new", project_label="Newest", account="work", total=60,
             input_tokens=40, output_tokens=20),
    event_at(NOW - timedelta(hours=6), project_key="new", project_label="Newest", account="work", total=30),
    event_at(NOW - timedelta(hours=5), project_key="boundary", project_label="Boundary", account="work", total=999),
]


class UsageSummaryTests(unittest.TestCase):
    def test_builds_authoritative_summary(self):
        summary = build_summary(
            EVENTS,
            window_name="5h",
            scope="current_project",
            accounts=["personal", "work", "work"],
            active_account="work",
            now=NOW,
        )
        self.assertEqual(summary["schema_version"], 1)
        self.assertEqual(summary["current_project"], {"key": "new", "label": "Newest"})
        self.assertEqual(summary["all_projects_window_total"], 160)
        self.assertEqual(summary["selected_scope_window_total"], 60)
        self.assertEqual(summary["current_project_cumulative_total"], 90)
        self.assertEqual(summary["accounts"], ["personal", "work"])
        self.assertEqual(summary["active_account"], "work")
        self.assertEqual(summary["available_detail_fields"], ["input_tokens", "output_tokens"])

    def test_account_filter_does_not_change_global_total(self):
        summary = build_summary(
            EVENTS, window_name="5h", scope="all_projects", accounts=[],
            active_account=None, selected_account="personal", now=NOW,
        )
        self.assertEqual(summary["selected_scope_window_total"], 100)
        self.assertEqual(summary["all_projects_window_total"], 160)

    def test_empty_and_diagnostics(self):
        empty = build_summary([], window_name="5h", scope="current_project", accounts=[], active_account=None, now=NOW)
        self.assertIsNone(empty["current_project"])
        summary = build_summary(EVENTS, window_name="5h", scope="current_project", accounts=[], active_account=None,
                                now=NOW, malformed_event_count=2)
        self.assertEqual(summary["diagnostics"], {"malformed_event_count": 2})

    def test_invalid_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            build_summary([], window_name="5h", scope="bad", accounts=[], active_account=None, now=NOW)


if __name__ == "__main__":
    unittest.main()
