#!/usr/bin/env bash

set -Eeuo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

python_bin=python
if [[ -x .venv/Scripts/python.exe ]]; then
  python_bin=.venv/Scripts/python.exe
elif [[ -x .venv/bin/python ]]; then
  python_bin=.venv/bin/python
fi

for command_name in git npm sha256sum; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'ERROR: required command is unavailable: %s\n' "$command_name" >&2
    exit 1
  fi
done

if ! "$python_bin" -c 'import sys; print(sys.version)' >/dev/null 2>&1; then
  printf 'ERROR: Python is unavailable. Activate the project virtual environment first.\n' >&2
  exit 1
fi

temp_root="$(mktemp -d "$repo_root/data/.phase0-4-acceptance.XXXXXX")"
cleanup() {
  case "$temp_root" in
    "$repo_root"/data/.phase0-4-acceptance.*)
      rm -rf -- "$temp_root"
      ;;
    *)
      printf 'WARNING: refusing to remove unexpected temporary path: %s\n' "$temp_root" >&2
      ;;
  esac
}
trap cleanup EXIT

export OFFLINE_DEMO_MODE=true
export API_DELAY_SECONDS=0
export ENVIRONMENT=development

section() {
  printf '\n==> %s\n' "$1"
}

section 'Phase 0: safe offline preflight'
"$python_bin" -m backend.app.preflight

section 'Phases 0-4: complete backend regression suite'
"$python_bin" -m pytest backend/tests -q

section 'Phase 2: validate checked-in synthetic dataset'
"$python_bin" -m data.generation.validate_dataset

section 'Phase 2: prove deterministic generation and public-copy parity'
"$python_bin" -m data.generation.generate_transactions \
  --output-dir "$temp_root/run-a" \
  --public-dir "$temp_root/public-a" \
  --initialize-output
"$python_bin" -m data.generation.generate_transactions \
  --output-dir "$temp_root/run-b" \
  --public-dir "$temp_root/public-b" \
  --initialize-output

sha_a="$(sha256sum "$temp_root/run-a/transactions_2025.csv" | awk '{print $1}')"
sha_b="$(sha256sum "$temp_root/run-b/transactions_2025.csv" | awk '{print $1}')"
[[ "$sha_a" == "$sha_b" ]] || {
  printf 'ERROR: deterministic generation hashes differ.\n' >&2
  exit 1
}
cmp "$temp_root/run-a/transactions_2025.csv" "$temp_root/public-a/transactions_2025.csv"
cmp "$temp_root/run-b/transactions_2025.csv" "$temp_root/public-b/transactions_2025.csv"
printf 'Deterministic transaction SHA-256: %s\n' "$sha_a"

section 'Phase 2: run the full offline evaluation twice'
"$python_bin" -m eval.run_eval \
  --dataset-dir data/synthetic \
  --report-dir "$temp_root/eval" \
  --repeats 2
"$python_bin" -c 'import json, pathlib; p=pathlib.Path(__import__("sys").argv[1]); d=json.loads(p.read_text(encoding="utf-8")); m=d["metadata"]; assert m["dataset_version"] == "smartwealth-synthetic-v2"; assert m["seed"] == 42; assert m["repeated_runs"] == 2; assert m["evaluated_sample_count_per_run"] == 300; assert all(value == 0.0 for value in d["variance"].values()); print("Evaluation metadata and zero repeated-run variance verified.")' "$temp_root/eval/eval_report.json"

section 'Phase 4: Python dependency audit'
"$python_bin" -m pip_audit -r backend/requirements.txt \
  --ignore-vuln PYSEC-2026-311 \
  --ignore-vuln PYSEC-2026-3813 \
  --ignore-vuln PYSEC-2026-3814 \
  --ignore-vuln PYSEC-2026-3815

section 'Phase 4: validate checked-in CycloneDX SBOM files'
"$python_bin" -c 'import json; json.load(open("sbom/backend.cdx.json", encoding="utf-8")); json.load(open("sbom/frontend.cdx.json", encoding="utf-8")); print("SBOM JSON valid.")'

section 'Phases 0-4: frontend lint and production build'
(
  cd frontend
  npm run lint
  npm run build
)

section 'Phase 4: frontend dependency audit'
(
  cd frontend
  npm audit --audit-level=high
)

section 'Phase 4: tracked-file secret-pattern scan'
set +e
git grep -n -I -E 'AIza[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' -- .
secret_scan_status=$?
set -e
if [[ $secret_scan_status -eq 0 ]]; then
  printf 'ERROR: possible credential material was found in tracked files.\n' >&2
  exit 1
elif [[ $secret_scan_status -ne 1 ]]; then
  printf 'ERROR: tracked-file secret scan could not complete.\n' >&2
  exit "$secret_scan_status"
fi
printf 'No tracked secret-pattern matches found.\n'

section 'Repository patch hygiene'
git diff --check

printf '\nPASS: every automatable Phase 0-4 guide check completed successfully.\n'
printf 'Manual-only checks still excluded: browser visual/accessibility review and optional live-provider behavior.\n'
