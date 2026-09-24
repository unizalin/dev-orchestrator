#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "$script_dir/.." && pwd)"
codex_root="${CODEX_HOME:-$HOME/.codex}"
target="$codex_root/skills/dev-orchestrator"
backup_root="$codex_root/backups/dev-orchestrator"
mode="install"

if [[ "${1:-}" == "--check" ]]; then
  mode="check"
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi

if [[ "$target" != "$codex_root/skills/dev-orchestrator" ]]; then
  echo "Refusing unexpected install target: $target" >&2
  exit 1
fi

DEV_ORCHESTRATOR_SKIP_USAGE_TESTS=1 "$script_dir/validate.sh" --skip-installed

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/dev-orchestrator-codex.XXXXXX")"
package="$temp_root/dev-orchestrator"

cleanup() {
  if [[ -d "$temp_root" ]]; then
    temp_parent="$(cd "$(dirname "$temp_root")" 2>/dev/null && pwd -P)"
    temp_name="$(basename "$temp_root")"
    expected_parent="$(cd "${TMPDIR:-/tmp}" 2>/dev/null && pwd -P)"
    resolved_temp="$(cd "$temp_root" 2>/dev/null && pwd -P)"
    if [[ -n "$resolved_temp" && "$resolved_temp" != "/" && "$temp_parent" == "$expected_parent" && "$temp_name" == dev-orchestrator-codex.* ]]; then
      if ! rm -rf -- "$resolved_temp"; then
        echo "Temporary directory retained for manual cleanup: $resolved_temp" >&2
      fi
    else
      echo "Temporary directory retained for manual cleanup (safety check failed): $temp_root" >&2
    fi
  fi
  return 0
}
trap cleanup EXIT

mkdir -p "$package/agents" "$package/references" "$package/scripts/dev_orchestrator_usage"
cp "$source_root/VERSION" "$package/VERSION"
cp "$source_root/config.yaml" "$package/config.yaml"
cp "$source_root/LICENSE" "$package/LICENSE"
cp "$source_root/adapters/codex/SKILL.md" "$package/SKILL.md"
cp "$source_root/adapters/codex/agents/openai.yaml" "$package/agents/openai.yaml"
cp "$source_root/core/routing.md" "$package/references/routing.md"
cp "$source_root/core/workflows.md" "$package/references/workflows.md"
cp "$source_root/core/model-roles.md" "$package/references/model-roles.md"
cp "$source_root/core/overrides.md" "$package/references/overrides.md"
cp "$source_root/core/handoff.md" "$package/references/handoff.md"
cp "$source_root/core/external-agents.md" "$package/references/external-agents.md"
cp "$source_root/scripts/dev-orchestrator-usage" "$package/scripts/dev-orchestrator-usage"
cp "$source_root/scripts/dev_orchestrator_usage/"*.py "$package/scripts/dev_orchestrator_usage/"
chmod 755 "$package/scripts/dev-orchestrator-usage"

if [[ "$mode" == "check" ]]; then
  if [[ ! -d "$target" ]]; then
    echo "Installed Codex Skill not found: $target" >&2
    exit 1
  fi
  diff -ru "$package" "$target"
  echo "Installed Codex adapter matches portable source."
  exit 0
fi

mkdir -p "$(dirname "$target")" "$backup_root"
backup_path=""
if [[ -e "$target" ]]; then
  backup_path="$backup_root/$(date +%Y%m%d-%H%M%S)-$$"
  mv "$target" "$backup_path"
  echo "Backed up existing Skill to: $backup_path"
fi

if mv "$package" "$target"; then
  echo "Installed Codex Skill to: $target"
else
  echo "Install failed; restoring previous Skill." >&2
  if [[ -n "$backup_path" && -d "$backup_path" && ! -e "$target" ]]; then
    mv "$backup_path" "$target"
  fi
  exit 1
fi

if DEV_ORCHESTRATOR_SKIP_USAGE_TESTS=1 "$script_dir/validate.sh"; then
  echo "Post-install validation passed."
else
  validation_status=$?
  failed_path="$backup_root/failed-$(date +%Y%m%d-%H%M%S)-$$"
  echo "Post-install validation failed; moving failed install to: $failed_path" >&2
  if [[ -e "$target" ]]; then
    mv "$target" "$failed_path"
  fi
  if [[ -n "$backup_path" && -d "$backup_path" && ! -e "$target" ]]; then
    mv "$backup_path" "$target"
    echo "Restored previous Skill from backup: $target" >&2
  fi
  exit "$validation_status"
fi
