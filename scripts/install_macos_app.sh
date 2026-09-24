#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source_root="$(cd "$script_dir/.." && pwd -P)"
app_dir="${DEV_ORCHESTRATOR_APP_DIR:-$HOME/Applications}"
destination="$app_dir/DevOrchestratorBar.app"
expected_destination="$app_dir/DevOrchestratorBar.app"

if [[ "$destination" != "$expected_destination" \
    || "$(basename "$destination")" != "DevOrchestratorBar.app" ]]; then
    printf 'error: refusing an unsafe installation destination: %s\n' "$destination" >&2
    exit 1
fi

"$source_root/scripts/build_macos_app.sh" release
source_app="$source_root/dist/DevOrchestratorBar.app"
if [[ ! -d "$source_app" ]]; then
    printf 'error: release build did not produce %s\n' "$source_app" >&2
    exit 1
fi

mkdir -p "$app_dir"
if [[ -e "$destination" || -L "$destination" ]]; then
    backup_root="$HOME/Library/Application Support/dev-orchestrator/backups/apps"
    mkdir -p "$backup_root"
    timestamp="$(date +%Y%m%d-%H%M%S)"
    backup_path="$backup_root/${timestamp}-DevOrchestratorBar.app"
    suffix=1
    while [[ -e "$backup_path" || -L "$backup_path" ]]; do
        backup_path="$backup_root/${timestamp}-${suffix}-DevOrchestratorBar.app"
        suffix=$((suffix + 1))
    done
    mv "$destination" "$backup_path"
fi

ditto "$source_app" "$destination"
printf 'installed %s\n' "$destination"
