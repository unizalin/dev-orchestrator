"""Safe readers and role attribution for Codex session JSONL files."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .model import TokenUsage, UsageEvent, subtract_usage
from .project import ProjectIdentity
from .state import AccountRegistry, Ledger, state_root


@dataclass(frozen=True)
class CodexSnapshot:
    timestamp: datetime
    session_id: str
    thread_id: str | None
    provider: str
    model: str
    usage: TokenUsage


@dataclass(frozen=True)
class TaskState:
    task_id: str
    project_key: str
    session_file: Path
    snapshot: CodexSnapshot
    started_at: datetime
    project_label: str = ""
    project_root: Path = Path()

    @classmethod
    def initial(cls, snapshot: CodexSnapshot, role: str = "implement", task_id: str | None = None,
                project_key: str = "", session_file: Path | None = None) -> "TaskState":
        return cls(task_id or os.environ.get("CODEX_THREAD_ID", ""), project_key,
                   session_file or Path(), snapshot, snapshot.timestamp)


def _time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _usage(raw: dict[str, Any] | None) -> TokenUsage:
    raw = raw or {}
    names = {
        "input_tokens": "input_tokens", "cached_input_tokens": "cache_read_tokens",
        "cache_write_input_tokens": "cache_write_tokens", "output_tokens": "output_tokens",
        "reasoning_output_tokens": "thinking_tokens", "total_tokens": "total_tokens",
    }
    values = {dest: raw.get(src) for src, dest in names.items()}
    return TokenUsage(**values)


def _metadata(line: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Return session id, thread id, provider, model without retaining payload."""
    typ, payload = line.get("type"), line.get("payload")
    if not isinstance(payload, dict):
        return None, None, None, None
    if typ == "session_meta":
        return (payload.get("session_id") or payload.get("id"), None,
                payload.get("model_provider"), None)
    if typ == "event_msg" and payload.get("type") == "thread_settings_applied":
        settings = payload.get("thread_settings")
        settings = settings if isinstance(settings, dict) else {}
        return (None, payload.get("thread_id"), settings.get("model_provider_id"), settings.get("model"))
    return None, None, None, None


def find_session_file(codex_home: Path, session_id: str | None = None, thread_id: str | None = None) -> Path | None:
    session_id = session_id or os.environ.get("CODEX_SESSION_ID")
    thread_id = thread_id or os.environ.get("CODEX_THREAD_ID")
    paths = sorted(Path(codex_home).glob("sessions/**/*.jsonl"))
    def lines(path: Path):
        try:
            with path.open(encoding="utf-8") as handle:
                yield from handle
        except (OSError, UnicodeDecodeError):
            return
    # First pass is deliberately limited to session_meta records.
    for path in paths:
        for line in lines(path):
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("type") != "session_meta":
                continue
            sid, _, _, _ = _metadata(data)
            if session_id and sid == session_id:
                return path
    # Only after no session id match, scan thread settings and stop at first hit.
    if thread_id:
        for path in paths:
            for line in lines(path):
                try: data = json.loads(line)
                except (json.JSONDecodeError, TypeError): continue
                if data.get("type") != "event_msg": continue
                _, tid, _, _ = _metadata(data)
                if tid == thread_id: return path
    return None


def read_snapshot(path: Path, model: str | None = None, provider: str | None = None) -> CodexSnapshot:
    session_id = ""
    thread_id = None
    selected_model = model or ""
    selected_provider = provider or ""
    timestamp = datetime.now(timezone.utc)
    latest = TokenUsage.unavailable()
    try:
        raw_lines = Path(path).open(encoding="utf-8")
    except (OSError, UnicodeError):
        return CodexSnapshot(timestamp, session_id, thread_id, selected_provider, selected_model, latest)
    with raw_lines:
      iterator = iter(raw_lines)
      while True:
        try:
            raw_line = next(iterator)
        except StopIteration:
            break
        except (OSError, UnicodeError):
            break
        try:
            line = json.loads(raw_line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(line, dict):
            continue
        stamp = line.get("timestamp")
        token_timestamp = None
        sid, tid, prov, mdl = _metadata(line)
        if sid: session_id = str(sid)
        if tid: thread_id = str(tid)
        if prov: selected_provider = str(prov)
        if mdl: selected_model = str(mdl)  # thread settings take precedence over caller fallback
        payload = line.get("payload")
        if isinstance(payload, dict) and line.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info")
            if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
                latest = _usage(info["total_token_usage"])
                if stamp is not None:
                    try: token_timestamp = _time(stamp)
                    except (TypeError, ValueError): pass
                if token_timestamp is not None: timestamp = token_timestamp
    return CodexSnapshot(timestamp, session_id, thread_id, selected_provider, selected_model, latest)


def checkpoint_from_snapshot(state: TaskState, snapshot: CodexSnapshot, role: str,
                             account_alias: str, project: ProjectIdentity) -> tuple[UsageEvent, TaskState]:
    # A snapshot without the provider total cannot establish a safe checkpoint;
    # do not turn absent data into a misleading zero delta.
    delta = None if snapshot.usage.total_tokens is None else subtract_usage(snapshot.usage, state.snapshot.usage)
    precision = "exact" if delta is not None else "unavailable"
    usage = delta if delta is not None else TokenUsage.unavailable()
    event = UsageEvent.new(project_key=project.key, project_label=project.label,
        account_alias=account_alias, task_id=state.task_id, thread_id=snapshot.thread_id,
        session_id=snapshot.session_id, conversation_id=None, role=role,
        provider=snapshot.provider, model=snapshot.model, source="codex-session",
        precision=precision, started_at=state.started_at, completed_at=snapshot.timestamp, usage=usage)
    baseline = snapshot if delta is not None else state.snapshot
    return event, TaskState(state.task_id, state.project_key, state.session_file, baseline, state.started_at, state.project_label, state.project_root)


def _state_path(root: Path, task_id: str) -> Path:
    return Path(root) / "active" / f"{task_id}.json"


def _write_state(root: Path, state: TaskState) -> None:
    path = _state_path(root, state.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"task_id": state.task_id, "project_key": state.project_key, "project_label": state.project_label, "project_root": str(state.project_root), "session_file": str(state.session_file),
            "started_at": state.started_at.isoformat(), "snapshot": {**asdict(state.snapshot), "timestamp": state.snapshot.timestamp.isoformat(), "usage": asdict(state.snapshot.usage)}}
    fd, name = tempfile.mkstemp(prefix=".task-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, separators=(",", ":")); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        try: os.unlink(name)
        except FileNotFoundError: pass


def start_task(snapshot: CodexSnapshot, project: ProjectIdentity, session_file: Path,
               root: Path | None = None, task_id: str | None = None, **_: Any) -> TaskState:
    resolved_root = Path(root) if root is not None else state_root()
    resolved_task = task_id or os.environ.get("CODEX_THREAD_ID") or snapshot.thread_id or snapshot.session_id
    if not resolved_task: raise ValueError("task id is required")
    task = TaskState(resolved_task, project.key, Path(session_file), snapshot, snapshot.timestamp, project.label, project.root)
    _write_state(resolved_root, task)
    return task


def checkpoint_task(state: TaskState, snapshot: CodexSnapshot, role: str, project: ProjectIdentity,
                    ledger: Ledger, account_registry: AccountRegistry, root: Path | None = None) -> tuple[UsageEvent, TaskState]:
    resolved_root = Path(root) if root is not None else state_root()
    event, updated = checkpoint_from_snapshot(state, snapshot, role, account_registry.active() or "unknown", project)
    ledger.append(event)
    _write_state(resolved_root, updated)
    return event, updated


def finish_task(state: TaskState, snapshot: CodexSnapshot, role: str, project: ProjectIdentity,
                ledger: Ledger, account_registry: AccountRegistry, root: Path | None = None) -> tuple[UsageEvent, TaskState]:
    resolved_root = Path(root) if root is not None else state_root()
    event, updated = checkpoint_task(state, snapshot, role, project, ledger, account_registry, resolved_root)
    source = _state_path(resolved_root, state.task_id)
    if source.exists():
        target = resolved_root / "completed" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
    return event, updated
