"""Optional tokscale quota integration (never required for token ledger use)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import shutil
import subprocess
from typing import Any


@dataclass(frozen=True)
class QuotaWindow:
    used_percent: float | None
    resets_at: datetime | None


@dataclass(frozen=True)
class AccountQuota:
    provider: str
    account_alias: str
    session: QuotaWindow
    weekly: QuotaWindow


@dataclass(frozen=True)
class QuotaResult:
    available: bool
    accounts: tuple[AccountQuota, ...]
    diagnostic: str | None = None

    @classmethod
    def unavailable(cls, diagnostic: str) -> "QuotaResult":
        return cls(False, (), diagnostic)


def _get(mapping: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _reset(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid reset time")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _window(raw: Any) -> QuotaWindow:
    if not isinstance(raw, dict):
        return QuotaWindow(None, None)
    used = _get(raw, "usedPercent", "used_percent")
    if used is not None:
        used = float(used)
    return QuotaWindow(used, _reset(_get(raw, "resetsAt", "resets_at")))


def parse_quotas(payload: Any) -> tuple[AccountQuota, ...]:
    if not isinstance(payload, dict):
        raise ValueError("tokscale payload must be an object")
    providers = payload.get("providers")
    if not isinstance(providers, list):
        raise ValueError("tokscale payload missing providers")
    result = []
    for item in providers:
        if not isinstance(item, dict):
            raise ValueError("invalid provider quota")
        account = _get(item, "account") or {}
        alias = _get(account, "name", "alias") if isinstance(account, dict) else None
        result.append(AccountQuota(
            provider=str(_get(item, "provider") or "unknown"),
            account_alias=str(alias or "default"),
            session=_window(_get(item, "session")),
            weekly=_window(_get(item, "weekly")),
        ))
    return tuple(result)


def load_quotas() -> QuotaResult:
    if shutil.which("tokscale") is None:
        return QuotaResult.unavailable("tokscale not installed")
    try:
        completed = subprocess.run(
            ["tokscale", "usage", "--json"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if completed.returncode != 0:
            return QuotaResult.unavailable(f"tokscale exited with status {completed.returncode}")
        accounts = parse_quotas(json.loads(completed.stdout))
        return QuotaResult(True, accounts)
    except subprocess.TimeoutExpired:
        return QuotaResult.unavailable("tokscale timed out")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return QuotaResult.unavailable(f"tokscale unavailable: {exc}")
