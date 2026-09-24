#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source_root="$(cd "$script_dir/.." && pwd -P)"
package_root="$source_root/macos/DevOrchestratorBar"

if [[ "$#" -gt 1 ]]; then
    printf 'usage: %s [debug|release]\n' "$0" >&2
    exit 2
fi
configuration="${1:-debug}"
case "$configuration" in
    debug|release) ;;
    *)
        printf 'error: configuration must be debug or release\n' >&2
        exit 2
        ;;
esac

dist_root="$source_root/dist"
app_path="$dist_root/DevOrchestratorBar.app"
if [[ "$dist_root" != "$source_root/dist" \
    || "$(dirname "$app_path")" != "$dist_root" \
    || "$(basename "$app_path")" != "DevOrchestratorBar.app" ]]; then
    printf 'error: refusing an unsafe app destination: %s\n' "$app_path" >&2
    exit 1
fi

info_plist="$package_root/Resources/Info.plist"
usage_wrapper="$source_root/scripts/dev-orchestrator-usage"
usage_module="$source_root/scripts/dev_orchestrator_usage"
for required_path in "$info_plist" "$usage_wrapper" "$usage_module"; do
    if [[ ! -e "$required_path" ]]; then
        printf 'error: required packaging input is missing: %s\n' "$required_path" >&2
        exit 1
    fi
done

swift build --package-path "$package_root" -c "$configuration"
bin_dir="$(swift build --package-path "$package_root" -c "$configuration" --show-bin-path)"
binary_path="$bin_dir/DevOrchestratorBar"
if [[ ! -x "$binary_path" ]]; then
    printf 'error: Swift build did not produce an executable: %s\n' "$binary_path" >&2
    exit 1
fi

staging_root="$(mktemp -d "${TMPDIR:-/tmp}/dev-orchestrator-bar-build.XXXXXX")"
trap 'rm -rf "$staging_root"' EXIT
staged_app="$staging_root/DevOrchestratorBar.app"
contents="$staged_app/Contents"
usage_cli="$contents/Resources/UsageCLI"
mkdir -p "$contents/MacOS" "$usage_cli"

cp "$binary_path" "$contents/MacOS/DevOrchestratorBar"
cp "$info_plist" "$contents/Info.plist"
cp "$usage_wrapper" "$usage_cli/dev-orchestrator-usage"
cp -R "$usage_module" "$usage_cli/dev_orchestrator_usage"
chmod 755 "$contents/MacOS/DevOrchestratorBar" "$usage_cli/dev-orchestrator-usage"

mkdir -p "$dist_root"
if [[ -e "$app_path" || -L "$app_path" ]]; then
    rm -rf "$app_path"
fi
mv "$staged_app" "$app_path"

codesign --force --deep --sign - "$app_path"
codesign --verify --deep --strict "$app_path"
printf 'built and signed %s (%s)\n' "$app_path" "$configuration"
