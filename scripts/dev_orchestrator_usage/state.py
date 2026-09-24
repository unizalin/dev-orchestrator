from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import os
import sys
import tempfile
from typing import Iterator

from .model import UsageEvent


def state_root(env: dict[str, str] | None = None, platform: str | None = None, home: Path | None = None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    override = env.get("DEV_ORCHESTRATOR_STATE_DIR")
    if override:
        return Path(override)
    if platform == "darwin":
        return home / "Library/Application Support/dev-orchestrator/usage"
    return Path(env.get("XDG_STATE_HOME", home / ".local/state")) / "dev-orchestrator/usage"


@contextmanager
def locked_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except BaseException:
        try:
            handle.close()
        except BaseException:
            pass
        raise

    def unlock() -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    try:
        yield handle
    except BaseException:
        # A body failure has priority over unlock and close failures.
        try:
            unlock()
        except BaseException:
            pass
        try:
            handle.close()
        except BaseException:
            pass
        raise
    else:
        try:
            unlock()
        except BaseException:
            # Unlock failure has priority, but close must still be attempted.
            try:
                handle.close()
            except BaseException:
                pass
            raise
        else:
            # With no earlier error, close failure must be observable.
            handle.close()


class AccountRegistry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "settings.json"

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            data = {}
        accounts = data.get("accounts", [])
        if not isinstance(accounts, list):
            accounts = []
        return {
            "enabled": bool(data.get("enabled", False)),
            "active_account": data.get("active_account"),
            "accounts": [str(alias) for alias in accounts],
        }

    def _write(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".settings-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, separators=(",", ":"), sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass

    def set_active(self, alias: str) -> None:
        if not alias or "@" in alias:
            raise ValueError("account alias must not be an email address")
        with locked_file(self.root / ".settings.lock"):
            data = self._read()
            if alias not in data["accounts"]:
                data["accounts"].append(alias)
            data["active_account"] = alias
            self._write(data)

    def enable(self) -> None:
        with locked_file(self.root / ".settings.lock"):
            data = self._read()
            data["enabled"] = True
            self._write(data)

    def is_enabled(self) -> bool:
        return bool(self._read()["enabled"])

    def accounts(self) -> list[str]:
        return list(self._read()["accounts"])

    def active(self) -> str | None:
        return self._read()["active_account"]


class Ledger:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.diagnostics: list[dict[str, str | int]] = []

    def _iter_events(self, collect_diagnostics: bool = True) -> Iterator[UsageEvent]:
        events_root = self.root / "events"
        if not events_root.exists():
            return
        seen: set[str] = set()
        for path in sorted(events_root.glob("*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as exc:
                if collect_diagnostics:
                    self.diagnostics.append({"file": str(path), "line": 0, "error": str(exc)})
                continue
            for line_number, line in enumerate(lines, 1):
                try:
                    event = UsageEvent.from_dict(json.loads(line))
                    if event.event_id in seen:
                        continue
                    seen.add(event.event_id)
                    yield event
                except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    if collect_diagnostics:
                        self.diagnostics.append({"file": str(path), "line": line_number, "error": str(exc)})

    def events(self) -> Iterator[UsageEvent]:
        self.diagnostics = []
        yield from self._iter_events()

    def append(self, event: UsageEvent) -> bool:
        month = event.completed_at.strftime("%Y-%m")
        path = self.root / "events" / f"{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked_file(self.root / ".ledger.lock"):
            if any(item.event_id == event.event_id for item in self._iter_events(False)):
                return False
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return True
