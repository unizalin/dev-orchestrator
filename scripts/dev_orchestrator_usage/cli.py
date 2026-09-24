from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from .aggregate import parse_window, render_all_projects_report, render_project_report
from .summary import build_summary
from .codex import (TaskState, checkpoint_task, find_session_file, finish_task,
                    read_snapshot, start_task)
from .external import ExternalCommandError, run_agy
from .model import EventContext, TokenUsage
from .project import resolve_project
from .state import AccountRegistry, Ledger, state_root
from .tokscale import load_quotas

EXIT_OK = 0
EXIT_USAGE_ERROR = 2
EXIT_TRACKING_DISABLED = 3
EXIT_DATA_UNAVAILABLE = 4
EXIT_EXTERNAL_FAILURE = 5
_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def _root(args) -> Path:
    return Path(args.state_dir).expanduser() if getattr(args, "state_dir", None) else state_root()


def _registry(args) -> AccountRegistry:
    return AccountRegistry(_root(args))


def _enabled(args) -> bool:
    return _registry(args).is_enabled()


def _require_enabled(args) -> bool:
    if not _enabled(args):
        print("tracking is not enabled; run setup first", file=sys.stderr)
        return False
    return True


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", type=Path, help=argparse.SUPPRESS)


def _launcher_target() -> Path:
    return Path(os.environ.get("DEV_ORCHESTRATOR_BIN_DIR", "~/.local/bin")).expanduser() / "dev-orchestrator-usage"


def _install_launcher() -> None:
    target = _launcher_target()
    source = Path(__file__).resolve().parents[1] / "dev-orchestrator-usage"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source:
            return
        raise OSError(f"refusing to overwrite existing path: {target}")
    target.symlink_to(source)


def _setup(args) -> int:
    if not _ALIAS.fullmatch(args.account):
        print("invalid account alias", file=sys.stderr)
        return EXIT_USAGE_ERROR
    try:
        install = args.install_launcher
        if not install and not args.no_launcher:
            if sys.stdin.isatty():
                install = input("Install dev-orchestrator-usage launcher? [y/N] ").strip().lower() in ("y", "yes")
        if install:
            _install_launcher()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE_ERROR
    registry = _registry(args)
    try:
        registry.set_active(args.account)
        registry.enable()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_DATA_UNAVAILABLE
    print(f"tracking enabled for {args.account}")
    return EXIT_OK


def _accounts(args) -> int:
    registry = _registry(args)
    if getattr(args, "account_action", None) == "set":
        if not registry.is_enabled():
            print("tracking is not enabled; run setup first", file=sys.stderr)
            return EXIT_TRACKING_DISABLED
        if not _ALIAS.fullmatch(args.alias):
            print("invalid account alias", file=sys.stderr)
            return EXIT_USAGE_ERROR
        try:
            registry.set_active(args.alias)
        except OSError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_DATA_UNAVAILABLE
    active = registry.active()
    for alias in registry.accounts():
        print(f"* {alias}" if alias == active else f"  {alias}")
    return EXIT_OK


def _report(args, all_projects: bool) -> int:
    if not _require_enabled(args):
        return EXIT_TRACKING_DISABLED
    try:
        window = parse_window(args.window)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE_ERROR
    root = _root(args)
    ledger = Ledger(root)
    events = list(ledger.events())
    if args.account:
        events = [e for e in events if e.account_alias == args.account]
    if all_projects:
        text = render_all_projects_report(events, window=window)
    else:
        project = resolve_project(Path.cwd())
        text = render_project_report(events, project_label=project.label, project_key=project.key, window=window)
    print(text)
    if not args.no_quota:
        quotas = load_quotas()
        if quotas.available:
            for quota in quotas.accounts:
                if args.account and quota.account_alias != args.account:
                    continue
                session = f"{quota.session.used_percent}%" if quota.session.used_percent is not None else "N/A"
                weekly = f"{quota.weekly.used_percent}%" if quota.weekly.used_percent is not None else "N/A"
                print(f"QUOTA {quota.account_alias} {quota.provider} SESSION {session} WEEKLY {weekly}")
        elif quotas.diagnostic:
            print(f"Note: quota unavailable ({quotas.diagnostic})", file=sys.stderr)
    if ledger.diagnostics:
        print(f"warning: skipped {len(ledger.diagnostics)} malformed event(s)", file=sys.stderr)
    return EXIT_OK


def _summary(args) -> int:
    if not _require_enabled(args):
        return EXIT_TRACKING_DISABLED
    try:
        parse_window(args.window)
        root = _root(args)
        registry = AccountRegistry(root)
        ledger = Ledger(root)
        events = list(ledger.events())
        project_override = resolve_project(args.project_path) if args.project_path else None
        payload = build_summary(
            events,
            window_name=args.window,
            scope=args.scope,
            accounts=registry.accounts(),
            active_account=registry.active(),
            selected_account=args.account,
            project_override=project_override,
            malformed_event_count=len(ledger.diagnostics),
        )
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return EXIT_OK
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE_ERROR
    except OSError as exc:
        print(f"summary: {exc}", file=sys.stderr)
        return EXIT_DATA_UNAVAILABLE


def _load_task(root: Path, task_id: str) -> TaskState:
    path = root / "active" / f"{task_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    snap = data["snapshot"]
    usage = TokenUsage(**snap["usage"])
    from .codex import CodexSnapshot
    from datetime import datetime
    snapshot = CodexSnapshot(datetime.fromisoformat(snap["timestamp"]), snap["session_id"], snap.get("thread_id"), snap["provider"], snap["model"], usage)
    return TaskState(data["task_id"], data["project_key"], Path(data["session_file"]), snapshot, datetime.fromisoformat(data["started_at"]), data.get("project_label", ""), Path(data.get("project_root", "")))


def _lifecycle(args, action: str) -> int:
    if not _require_enabled(args):
        return EXIT_TRACKING_DISABLED
    root = _root(args)
    try:
        project = resolve_project(Path.cwd())
        task_id = args.task_id or os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
        if action == "task-start":
            session = find_session_file(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
            if session is None:
                raise FileNotFoundError("Codex session file not found")
            start_task(read_snapshot(session), project, session, root=root, task_id=task_id)
        else:
            if not task_id:
                raise ValueError("task id is required")
            state = _load_task(root, task_id)
            project = type(project)(state.project_key, state.project_label or project.label, state.project_root or project.root)
            snapshot = read_snapshot(state.session_file)
            ledger = Ledger(root)
            registry = AccountRegistry(root)
            if action == "checkpoint":
                checkpoint_task(state, snapshot, args.role, project, ledger, registry, root=root)
            else:
                finish_task(state, snapshot, args.role, project, ledger, registry, root=root)
        return EXIT_OK
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"{action}: {exc}", file=sys.stderr)
        return EXIT_DATA_UNAVAILABLE


def _run_agy(args) -> int:
    if not _require_enabled(args):
        return EXIT_TRACKING_DISABLED
    try:
        project = resolve_project(Path.cwd()); registry = _registry(args)
        context = EventContext(
            project_key=project.key, project_label=project.label,
            account_alias=registry.active() or "unknown",
            task_id=os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID") or "",
            thread_id=os.environ.get("CODEX_THREAD_ID"),
            session_id=os.environ.get("CODEX_SESSION_ID") or "",
            role=args.role, provider="google", model=args.model,
        )
        response, event = run_agy(Path(args.prompt_file), role=args.role, model=args.model, effort=args.effort, context=context)
        Ledger(_root(args)).append(event)
        print(response, end="" if response.endswith("\n") else "\n")
        return EXIT_OK
    except ExternalCommandError as exc:
        print(f"run-agy: {exc}", file=sys.stderr); return EXIT_EXTERNAL_FAILURE
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"run-agy: {exc}", file=sys.stderr); return EXIT_DATA_UNAVAILABLE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-orchestrator-usage")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("setup"); p.add_argument("--account", required=True); launch = p.add_mutually_exclusive_group(); launch.add_argument("--install-launcher", action="store_true"); launch.add_argument("--no-launcher", action="store_true"); _add_common(p)
    p = sub.add_parser("accounts"); _add_common(p); asp = p.add_subparsers(dest="account_action"); sp = asp.add_parser("set"); sp.add_argument("alias"); _add_common(sp)
    for name in ("current", "all"):
        p = sub.add_parser(name); p.add_argument("--window", default="5h"); p.add_argument("--account"); p.add_argument("--no-quota", action="store_true"); _add_common(p)
    p = sub.add_parser("summary"); p.add_argument("--scope", choices=("current_project", "all_projects"), default="current_project"); p.add_argument("--window", default="5h"); p.add_argument("--account"); p.add_argument("--project-path", type=Path); _add_common(p)
    for name in ("task-start", "checkpoint", "finish"):
        p = sub.add_parser(name); p.add_argument("--task-id"); p.add_argument("--role", default="implement"); _add_common(p)
    p = sub.add_parser("run-agy"); p.add_argument("--role", required=True); p.add_argument("--model", required=True); p.add_argument("--effort", default="high"); p.add_argument("--prompt-file", required=True); _add_common(p)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if not args.command:
        parser.print_help(); return EXIT_USAGE_ERROR
    if args.command == "setup": return _setup(args)
    if args.command == "accounts": return _accounts(args)
    if args.command == "current": return _report(args, False)
    if args.command == "all": return _report(args, True)
    if args.command == "summary": return _summary(args)
    if args.command in ("task-start", "checkpoint", "finish"): return _lifecycle(args, args.command)
    if args.command == "run-agy": return _run_agy(args)
    return EXIT_USAGE_ERROR
