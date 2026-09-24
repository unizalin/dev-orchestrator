#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "$script_dir/.." && pwd)"
dist_root="$source_root/dist"
target="$dist_root/chatgpt"
backup_root="$dist_root/.backups"

"$script_dir/validate.sh" --skip-installed

python_bin=""
for candidate in /usr/bin/python3 "$(command -v python3 2>/dev/null || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo "Export validation requires Python with PyYAML." >&2
  exit 1
fi

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/dev-orchestrator-chatgpt.XXXXXX")"
new_dist="$temp_root/chatgpt"
skill_package="$new_dist/skill/dev-orchestrator"

cleanup() {
  if [[ -d "$temp_root" ]]; then
    rmdir "$temp_root" 2>/dev/null || {
      if command -v trash >/dev/null 2>&1; then
        trash "$temp_root"
      else
        echo "Temporary directory retained for manual cleanup: $temp_root" >&2
      fi
    }
  fi
}
trap cleanup EXIT

mkdir -p "$skill_package/core"
cp "$source_root/adapters/chatgpt/SKILL.md" "$skill_package/SKILL.md"
cp "$source_root/adapters/chatgpt/INSTRUCTIONS.md" "$skill_package/INSTRUCTIONS.md"
cp "$source_root/adapters/chatgpt/SPEC_TEMPLATE.md" "$skill_package/SPEC_TEMPLATE.md"
cp "$source_root/adapters/chatgpt/HANDOFF_REVIEW.md" "$skill_package/HANDOFF_REVIEW.md"
cp "$source_root/config.yaml" "$skill_package/config.yaml"
cp "$source_root/LICENSE" "$skill_package/LICENSE"
cp "$source_root/core/"*.md "$skill_package/core/"

cp "$source_root/adapters/chatgpt/INSTRUCTIONS.md" "$new_dist/INSTRUCTIONS.md"
cp "$source_root/adapters/chatgpt/SPEC_TEMPLATE.md" "$new_dist/SPEC_TEMPLATE.md"
cp "$source_root/adapters/chatgpt/HANDOFF_REVIEW.md" "$new_dist/HANDOFF_REVIEW.md"
cp "$source_root/core/workflows.md" "$new_dist/CORE_WORKFLOW_SUMMARY.md"

validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [[ -f "$validator" ]]; then
  "$python_bin" "$validator" "$skill_package"
fi

(
  cd "$new_dist/skill"
  /usr/bin/zip -qry "$new_dist/dev-orchestrator-chatgpt-skill.zip" dev-orchestrator
)

mkdir -p "$dist_root" "$backup_root"
backup_path=""
if [[ -e "$target" ]]; then
  backup_path="$backup_root/chatgpt-$(date +%Y%m%d-%H%M%S)-$$"
  mv "$target" "$backup_path"
  echo "Backed up previous ChatGPT export to: $backup_path"
fi

if mv "$new_dist" "$target"; then
  echo "Exported ChatGPT adapter to: $target"
else
  echo "Export failed; restoring previous ChatGPT export." >&2
  if [[ -n "$backup_path" && -d "$backup_path" && ! -e "$target" ]]; then
    mv "$backup_path" "$target"
  fi
  exit 1
fi

echo "Uploadable Skill package: $target/dev-orchestrator-chatgpt-skill.zip"
