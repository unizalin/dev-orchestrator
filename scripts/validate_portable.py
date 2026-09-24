#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


EXPECTED_ROLES = [
    "spec",
    "implement",
    "quick_implement",
    "investigate",
    "quick_review",
    "escalate",
    "independent_review",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def route(config: dict, case: str, failures: int = 0, overrides: set[str] | None = None) -> dict:
    overrides = overrides or set()
    external_allowed = not ({"openai_only", "no_external"} & overrides)
    write_allowed = not ({"analysis_only", "no_code"} & overrides)

    if case == "trivial":
        roles = ["quick_implement"] if write_allowed else []
    elif case == "clear_feature":
        roles = ["implement"] if write_allowed else []
    elif case == "unknown_bug":
        roles = (["investigate"] if external_allowed else []) + (["implement"] if write_allowed else [])
    elif case == "large_refactor":
        roles = (["investigate"] if external_allowed else []) + ["spec"]
        if write_allowed:
            roles.append("implement")
        if external_allowed:
            roles.append("quick_review")
    else:
        raise AssertionError(f"unknown route case: {case}")

    threshold = config["limits"]["sol_min_failed_attempts"]
    sol_allowed = "no_sol" not in overrides
    if failures >= threshold and sol_allowed and write_allowed:
        roles.append("escalate")

    return {"roles": roles, "write_allowed": write_allowed, "external_allowed": external_allowed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()

    required_files = [
        "VERSION",
        "CHANGELOG.md",
        "LICENSE",
        "README.md",
        "config.yaml",
        "core/routing.md",
        "core/workflows.md",
        "core/model-roles.md",
        "core/overrides.md",
        "core/handoff.md",
        "core/external-agents.md",
        "adapters/codex/SKILL.md",
        "adapters/codex/agents/openai.yaml",
        "adapters/chatgpt/SKILL.md",
        "adapters/chatgpt/INSTRUCTIONS.md",
        "adapters/chatgpt/SPEC_TEMPLATE.md",
        "adapters/chatgpt/HANDOFF_REVIEW.md",
        "scripts/install_codex.sh",
        "scripts/validate.sh",
        "scripts/export_chatgpt.sh",
        "scripts/dev-orchestrator-usage",
        "scripts/dev_orchestrator_usage/cli.py",
        "scripts/dev_orchestrator_usage/summary.py",
        "scripts/build_macos_app.sh",
        "scripts/install_macos_app.sh",
        "macos/DevOrchestratorBar/Package.swift",
        "macos/DevOrchestratorBar/Resources/Info.plist",
    ]
    missing = [path for path in required_files if not (root / path).is_file()]
    require(not missing, f"missing required files: {missing}")

    version = (root / "VERSION").read_text().strip()
    require(version == "2.2.0", f"unexpected VERSION: {version}")

    config = yaml.safe_load((root / "config.yaml").read_text())
    require(config["portable_version"] == version, "VERSION and config portable_version differ")
    plist = (root / "macos/DevOrchestratorBar/Resources/Info.plist").read_text()
    require("<key>CFBundleShortVersionString</key>" in plist, "Info.plist lacks bundle version")
    require("<string>2.2.0</string>" in plist, "Info.plist version must be 2.2.0")
    require(config["usage_tracking"]["mode"] == "opt_in", "usage tracking must be opt-in")
    require(list(config["roles"].keys()) == EXPECTED_ROLES, "config role set/order changed")
    require(config["limits"]["sol_min_failed_attempts"] == 2, "Sol threshold must default to 2")
    for role in ("investigate", "quick_review", "independent_review"):
        require(config["roles"][role]["access"] == "read-only", f"{role} must be read-only")
        require(config["roles"][role]["resolve_at_runtime"] is True, f"{role} must resolve at runtime")

    for adapter in ("adapters/codex/SKILL.md", "adapters/chatgpt/SKILL.md"):
        text = (root / adapter).read_text()
        require(text.startswith("---\n"), f"{adapter} lacks YAML frontmatter")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        require(frontmatter.get("name") == "dev-orchestrator", f"{adapter} has wrong skill name")
        require(bool(frontmatter.get("description")), f"{adapter} lacks description")

    ids = [
        "gpt-6-astra",
        "gpt-5.6-luna",
        "gemini-3.1-pro-high",
        "gemini-3.8-flash-high",
        "gpt-5.6-sol",
        "claude-sonnet-4-6",
    ]
    core_policy = "\n".join(
        (root / path).read_text()
        for path in (
            "core/routing.md",
            "core/workflows.md",
            "core/model-roles.md",
            "core/overrides.md",
            "core/handoff.md",
        )
    )
    require(not any(model_id in core_policy for model_id in ids), "model IDs leaked into core workflow policy")

    tests: list[tuple[str, callable]] = []

    tests.append(("trivial edit routes to quick_implement", lambda: require(
        route(config, "trivial")["roles"] == ["quick_implement"], "unexpected trivial route"
    )))
    tests.append(("clear feature routes to implement", lambda: require(
        route(config, "clear_feature")["roles"] == ["implement"], "unexpected clear-feature route"
    )))
    tests.append(("unknown bug routes investigate then implement", lambda: require(
        route(config, "unknown_bug")["roles"] == ["investigate", "implement"], "unexpected bug route"
    )))
    tests.append(("large refactor includes spec, investigation, implementation, and review", lambda: require(
        route(config, "large_refactor")["roles"] == ["investigate", "spec", "implement", "quick_review"],
        "unexpected large-refactor route"
    )))
    tests.append(("failure_count 0 does not use Sol", lambda: require(
        "escalate" not in route(config, "unknown_bug", failures=0)["roles"], "Sol used at failure_count 0"
    )))
    tests.append(("failure_count 1 does not use Sol", lambda: require(
        "escalate" not in route(config, "unknown_bug", failures=1)["roles"], "Sol used at failure_count 1"
    )))
    tests.append(("failure_count 2 allows Sol", lambda: require(
        "escalate" in route(config, "unknown_bug", failures=2)["roles"], "Sol not allowed at threshold"
    )))
    tests.append(("No Sol disables escalation regardless of threshold", lambda: require(
        "escalate" not in route(config, "unknown_bug", failures=99, overrides={"no_sol"})["roles"],
        "No Sol override ignored"
    )))
    tests.append(("Analysis only prevents repository writes", lambda: require(
        route(config, "clear_feature", overrides={"analysis_only"})["write_allowed"] is False,
        "Analysis only still allows writes"
    )))
    tests.append(("OpenAI-only removes agy-bound roles", lambda: require(
        all(config["roles"][role]["provider"] != "antigravity"
            for role in route(config, "large_refactor", overrides={"openai_only"})["roles"]),
        "OpenAI-only retained an Antigravity role"
    )))

    handoff = (root / "core/handoff.md").read_text()
    handoff_requirements = [
        "# DEV HANDOFF", "## Goal", "## Status", "COMPLETED", "PARTIAL", "BLOCKED",
        "## Routing Used", "## Changed Files", "## Tests / Build", "PASS | FAIL | NOT RUN",
        "## Acceptance Criteria", "## RETURN TO CHATGPT", "=== RETURN TO CHATGPT ===",
        "=== END RETURN ===",
    ]
    tests.append(("handoff template is complete and evidence-aware", lambda: require(
        all(item in handoff for item in handoff_requirements), "handoff template is incomplete"
    )))

    chatgpt_text = "\n".join(
        (root / path).read_text().lower()
        for path in ("adapters/chatgpt/SKILL.md", "adapters/chatgpt/INSTRUCTIONS.md")
    )
    tests.append(("ChatGPT adapter does not claim local repository or agy access", lambda: require(
        all(item in chatgpt_text for item in ("do not claim", "local repository", "~/.codex/skills", "agy")),
        "ChatGPT capability boundary is incomplete"
    )))

    failures: list[str] = []
    for index, (name, test) in enumerate(tests, start=1):
        try:
            test()
            print(f"[PASS] TEST {index}: {name}")
        except Exception as exc:  # validation should report all failures
            failures.append(f"TEST {index}: {name}: {exc}")
            print(f"[FAIL] TEST {index}: {name}: {exc}")

    if failures:
        print("\nValidation failures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Portable structure, YAML, bindings, and TEST 1-12: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
