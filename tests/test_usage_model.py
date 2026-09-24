from datetime import datetime, timezone
from unittest import TestCase

from scripts.dev_orchestrator_usage.model import (
    TokenUsage,
    UsageEvent,
    normalize_optional_int,
    subtract_usage,
)


class UsageModelTests(TestCase):
    def test_normalize_optional_int_accepts_none(self):
        self.assertIsNone(normalize_optional_int(None))

    def test_normalize_optional_int_accepts_integer(self):
        self.assertEqual(normalize_optional_int(42), 42)

    def test_normalize_optional_int_parses_numeric_string(self):
        self.assertEqual(normalize_optional_int("42"), 42)

    def test_normalize_optional_int_rejects_negative(self):
        with self.assertRaises(ValueError):
            normalize_optional_int(-1)

    def test_normalize_optional_int_rejects_non_numeric_value(self):
        with self.assertRaises(ValueError):
            normalize_optional_int("not-a-number")

    def test_total_is_provider_value_not_sum_of_composition_columns(self):
        usage = TokenUsage(
            input_tokens=100,
            cache_read_tokens=80,
            cache_write_tokens=0,
            output_tokens=20,
            thinking_tokens=10,
            total_tokens=120,
        )
        self.assertEqual(usage.total_tokens, 120)

    def test_subtract_usage_preserves_provider_total_semantics(self):
        before = TokenUsage(100, 80, 0, 20, 10, 120)
        after = TokenUsage(160, 120, 0, 35, 15, 195)
        self.assertEqual(subtract_usage(after, before), TokenUsage(60, 40, 0, 15, 5, 75))

    def test_negative_delta_returns_unavailable(self):
        before = TokenUsage(100, 0, 0, 20, 0, 120)
        after = TokenUsage(90, 0, 0, 10, 0, 100)
        self.assertIsNone(subtract_usage(after, before))

    def test_subtract_usage_preserves_known_deltas_when_optional_fields_missing(self):
        before = TokenUsage(100, None, 0, 20, None, 120)
        after = TokenUsage(160, None, 0, 35, None, 195)
        self.assertEqual(
            subtract_usage(after, before),
            TokenUsage(60, None, 0, 15, None, 75),
        )

    def test_event_round_trip_omits_prompt_content(self):
        event = UsageEvent.new(
            project_key="p1",
            project_label="demo",
            account_alias="personal",
            task_id="t1",
            thread_id="th1",
            session_id="s1",
            conversation_id=None,
            role="implement",
            provider="openai",
            model="gpt-5.6-luna",
            source="codex-session",
            precision="exact",
            started_at=datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 9, 24, 0, 1, tzinfo=timezone.utc),
            usage=TokenUsage(100, 80, 0, 20, 10, 120),
        )
        restored = UsageEvent.from_dict(event.to_dict())
        self.assertEqual(restored, event)
        self.assertNotIn("prompt", event.to_dict())
        self.assertNotIn("response", event.to_dict())
