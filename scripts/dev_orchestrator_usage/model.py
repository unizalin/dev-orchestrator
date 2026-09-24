from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal, Optional

Precision = Literal["exact", "unavailable"]


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: Optional[int]
    cache_read_tokens: Optional[int]
    cache_write_tokens: Optional[int]
    output_tokens: Optional[int]
    thinking_tokens: Optional[int]
    total_tokens: Optional[int]

    @classmethod
    def unavailable(cls) -> "TokenUsage":
        return cls(None, None, None, None, None, None)


@dataclass(frozen=True)
class EventContext:
    project_key: str
    project_label: str
    account_alias: str
    task_id: str
    thread_id: Optional[str]
    session_id: str
    role: str
    provider: str
    model: str


def normalize_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError("token counts cannot be negative")
    return parsed


def subtract_usage(after: TokenUsage, before: TokenUsage) -> Optional[TokenUsage]:
    values = []
    for newer, older in zip(asdict(after).values(), asdict(before).values()):
        if newer is None or older is None:
            values.append(None)
            continue
        if newer < older:
            return None
        values.append(newer - older)
    return TokenUsage(*values)


@dataclass(frozen=True)
class UsageEvent:
    schema_version: int
    event_id: str
    recorded_at: datetime
    started_at: datetime
    completed_at: datetime
    project_key: str
    project_label: str
    account_alias: str
    task_id: str
    thread_id: Optional[str]
    session_id: str
    conversation_id: Optional[str]
    role: str
    provider: str
    model: str
    source: str
    precision: Precision
    usage: TokenUsage

    @classmethod
    def new(cls, **values: Any) -> "UsageEvent":
        identity = "|".join(
            str(values.get(k, ""))
            for k in (
                "project_key",
                "account_alias",
                "task_id",
                "session_id",
                "conversation_id",
                "role",
                "started_at",
                "completed_at",
            )
        )
        return cls(
            schema_version=1,
            event_id=sha256(identity.encode("utf-8")).hexdigest(),
            recorded_at=datetime.now(timezone.utc),
            **values,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("recorded_at", "started_at", "completed_at"):
            data[key] = data[key].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UsageEvent":
        copy = dict(data)
        copy["usage"] = TokenUsage(**copy["usage"])
        for key in ("recorded_at", "started_at", "completed_at"):
            copy[key] = datetime.fromisoformat(copy[key])
        return cls(**copy)
