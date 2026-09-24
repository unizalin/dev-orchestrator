#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "$script_dir/.." && pwd)"
skip_installed=false
live_agy=false

for arg in "$@"; do
  case "$arg" in
    --skip-installed) skip_installed=true ;;
    --live-agy) live_agy=true ;;
    *) echo "Usage: $0 [--skip-installed] [--live-agy]" >&2; exit 2 ;;
  esac
done

python_bin=""
for candidate in /usr/bin/python3 "$(command -v python3 2>/dev/null || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c 'import yaml' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo "Validation requires Python with PyYAML." >&2
  exit 1
fi

"$python_bin" "$script_dir/validate_portable.py" "$source_root"

if [[ "${DEV_ORCHESTRATOR_SKIP_USAGE_TESTS:-0}" != "1" ]]; then
  DEV_ORCHESTRATOR_SKIP_USAGE_TESTS=1 "$python_bin" -m unittest discover -s "$source_root/tests" -p 'test_usage_*.py' -v
fi

validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [[ -f "$validator" ]]; then
  "$python_bin" "$validator" "$source_root/adapters/codex"
  "$python_bin" "$validator" "$source_root/adapters/chatgpt"
else
  echo "Official quick_validate.py not found; portable checks still passed." >&2
fi

if ! command -v agy >/dev/null 2>&1; then
  echo "agy executable not found." >&2
  exit 1
fi
echo "agy executable: $(command -v agy)"

if [[ "$live_agy" == true ]]; then
  agy_output="$(agy models)"
  printf '%s\n' "$agy_output"
  while IFS= read -r model_id; do
    if awk -v id="$model_id" '$1 == id { found=1 } END { exit !found }' <<<"$agy_output"; then
      echo "agy preferred model available: $model_id"
    else
      echo "agy preferred model unavailable; runtime same-role fallback required: $model_id" >&2
    fi
  done < <("$python_bin" -c 'import sys,yaml; c=yaml.safe_load(open(sys.argv[1])); [print(x) for x in c["discovery"]["antigravity"]["observed_preferred_models"]]' "$source_root/config.yaml")
  echo "agy live validation: PASS"
fi

if [[ "$skip_installed" == false ]]; then
  "$script_dir/install_codex.sh" --check >/dev/null
  echo "[PASS] TEST 13: source and installed Codex adapter have no meaningful drift"
  echo "All 13 validation tests: PASS"
else
  echo "Installed-adapter drift check skipped for pre-install validation."
fi
