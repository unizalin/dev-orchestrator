from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model import EventContext, TokenUsage, UsageEvent, normalize_optional_int


class ExternalCommandError(RuntimeError):
    def __init__(self, returncode: int, stderr: str):
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"agy exited with status {returncode}: {stderr or 'no error output'}")


def normalize_agy_result(payload: dict[str, Any], context: EventContext, *,
                         started_at: datetime | None = None,
                         completed_at: datetime | None = None) -> UsageEvent:
    if not isinstance(payload, dict):
        raise ValueError("agy result must be a JSON object")
    if payload.get("status") != "SUCCESS":
        raise ValueError(f"agy invocation was not successful: {payload.get('status')}")
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        raise ValueError("agy result is missing usage")
    usage = TokenUsage(
        normalize_optional_int(raw.get("input_tokens")),
        normalize_optional_int(raw.get("cache_read_tokens")),
        normalize_optional_int(raw.get("cache_write_tokens")),
        normalize_optional_int(raw.get("output_tokens")),
        normalize_optional_int(raw.get("thinking_tokens")),
        normalize_optional_int(raw.get("total_tokens")),
    )
    started = started_at or datetime.now(timezone.utc)
    completed = completed_at or datetime.now(timezone.utc)
    return UsageEvent.new(
        project_key=context.project_key, project_label=context.project_label,
        account_alias=context.account_alias, task_id=context.task_id,
        thread_id=context.thread_id, session_id=context.session_id,
        conversation_id=payload.get("conversation_id"), role=context.role,
        provider=context.provider, model=context.model, source="agy",
        precision="exact" if usage.total_tokens is not None else "unavailable",
        started_at=started, completed_at=completed, usage=usage,
    )


def run_agy(prompt_file: Path, *, role: str, model: str, effort: str,
            context: EventContext) -> tuple[str, UsageEvent]:
    command = ["agy", "--print", prompt_file.read_text(encoding="utf-8"),
               "--model", model, "--effort", effort, "--mode", "plan", "--output-format", "json",
               "--sandbox", "--print-timeout", "0s"]
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ExternalCommandError(result.returncode, result.stderr.strip())
    payload = json.loads(result.stdout)
    event = normalize_agy_result(payload, context=replace(context, role=role, model=model), started_at=started,
                                 completed_at=datetime.now(timezone.utc))
    return payload.get("response") or "", event
