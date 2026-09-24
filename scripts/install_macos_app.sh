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

stage_dir=""
staged_app=""
backup_path=""
backup_created=0

cleanup_staging() {
    [[ -n "$stage_dir" ]] || return 0

    local stage_real stage_parent stage_real_parent stage_base
    stage_real="$(realpath "$stage_dir" 2>/dev/null || true)"
    stage_parent="$(realpath "$app_dir" 2>/dev/null || true)"
    stage_real_parent="$(dirname "$stage_real" 2>/dev/null || true)"
    stage_base="$(basename "$stage_real" 2>/dev/null || true)"
    if [[ -n "$stage_real" && -n "$stage_parent" \
        && "$stage_real_parent" == "$stage_parent" \
        && "$stage_real" != "$stage_parent" \
        && "$stage_real" != "/" \
        && "$stage_real" != "$app_dir" \
        && "$stage_base" =~ ^\.DevOrchestratorBar\.install\.[A-Za-z0-9]+$ ]]; then
        rm -rf -- "$stage_real"
    else
        printf 'warning: refusing to remove unsafe staging path: %s\n' "$stage_real" >&2
    fi
}

on_exit() {
    local status=$?
    trap - EXIT

    if [[ "$status" -ne 0 && "$backup_created" -eq 1 ]]; then
        printf 'installation failed; restoring backup: %s -> %s\n' "$backup_path" "$destination" >&2
        if [[ -e "$destination" || -L "$destination" ]]; then
            if ! rm -rf -- "$destination"; then
                printf 'error: could not remove failed destination: %s\n' "$destination" >&2
            fi
        fi
        if [[ -e "$backup_path" || -L "$backup_path" ]]; then
            if mv "$backup_path" "$destination"; then
                printf 'restored previous app: %s -> %s\n' "$backup_path" "$destination" >&2
                backup_created=0
            else
                printf 'error: restore failed; backup remains at: %s\n' "$backup_path" >&2
            fi
        else
            printf 'error: backup no longer exists; expected at: %s\n' "$backup_path" >&2
        fi
    fi

    cleanup_staging || true
    exit "$status"
}
trap on_exit EXIT

stage_dir="$(mktemp -d "$app_dir/.DevOrchestratorBar.install.XXXXXX")"
staged_app="$stage_dir/DevOrchestratorBar.app"

ditto "$source_app" "$staged_app"
codesign --verify --deep --strict "$staged_app"

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
    backup_created=1
    printf 'backed up existing app: %s -> %s\n' "$destination" "$backup_path"
fi

mv "$staged_app" "$destination"
printf 'installed %s\n' "$destination"
