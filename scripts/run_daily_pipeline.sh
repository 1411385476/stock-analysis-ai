#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/venv312/bin/python"

RUN_DATE="$(date +%Y%m%d)"
RUN_TS="$(date +%Y%m%d_%H%M%S)"

SINGLE_SYMBOL="600519"
PORTFOLIO_SYMBOLS="600519,000001,300750"
UNIVERSE="hs300"
TOP_N="20"

BT_FEE_RATE="0.001"
BT_SLIPPAGE_BPS="8"
BT_MIN_HOLD_DAYS="3"
BT_SIGNAL_CONFIRM_DAYS="2"
BT_MAX_POSITIONS="2"

MAX_RETRIES="1"
RETRY_DELAY_SEC="5"
DRY_RUN="0"

SKIP_SYNC="0"
SKIP_SCAN="0"
SKIP_ANALYSIS="0"
SKIP_PORTFOLIO="0"
SKIP_DASHBOARD="0"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_daily_pipeline.sh [options]

Options:
  --date YYYYMMDD                Run date tag (default: today)
  --python /path/to/python       Python binary (default: venv312/bin/python)
  --single-symbol 600519         Single-stock analysis symbol
  --portfolio-symbols A,B,C      Portfolio symbols for backtest/risk
  --universe hs300               Universe for scan
  --top 20                       Top N candidates for scan
  --max-retries 1                Retry times per step after first failure
  --retry-delay-sec 5            Retry delay seconds
  --skip-sync                    Skip snapshot sync step
  --skip-scan                    Skip candidate scan step
  --skip-analysis                Skip single analysis step
  --skip-portfolio               Skip portfolio backtest + risk step
  --skip-dashboard               Skip dashboard generation step
  --dry-run                      Print commands only, do not execute
  -h, --help                     Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      RUN_DATE="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --single-symbol)
      SINGLE_SYMBOL="${2:-}"
      shift 2
      ;;
    --portfolio-symbols)
      PORTFOLIO_SYMBOLS="${2:-}"
      shift 2
      ;;
    --universe)
      UNIVERSE="${2:-}"
      shift 2
      ;;
    --top)
      TOP_N="${2:-}"
      shift 2
      ;;
    --max-retries)
      MAX_RETRIES="${2:-}"
      shift 2
      ;;
    --retry-delay-sec)
      RETRY_DELAY_SEC="${2:-}"
      shift 2
      ;;
    --skip-sync)
      SKIP_SYNC="1"
      shift
      ;;
    --skip-scan)
      SKIP_SCAN="1"
      shift
      ;;
    --skip-analysis)
      SKIP_ANALYSIS="1"
      shift
      ;;
    --skip-portfolio)
      SKIP_PORTFOLIO="1"
      shift
      ;;
    --skip-dashboard)
      SKIP_DASHBOARD="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[E_INPUT] Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! "${RUN_DATE}" =~ ^[0-9]{8}$ ]]; then
  echo "[E_INPUT] --date must be YYYYMMDD"
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[E_INPUT] python binary not executable: ${PYTHON_BIN}"
  exit 1
fi

RUN_ID="${RUN_TS}"
RUN_DIR="${ROOT_DIR}/data/pipeline_runs/${RUN_DATE}/${RUN_TS}"
RUN_DATA_DIR="${RUN_DIR}/data"
RUN_LOG_DIR="${RUN_DIR}/logs"
RUN_DASHBOARD_DIR="${RUN_DIR}/dashboard"

HEALTH_FILE="${RUN_DIR}/pipeline_health.json"
LATEST_HEALTH_FILE="${ROOT_DIR}/data/pipeline_runs/latest_health.json"
PIPELINE_LOG="${RUN_DIR}/pipeline.log"
STEP_RESULT_TSV="${RUN_DIR}/steps.tsv"

mkdir -p "${RUN_DATA_DIR}" "${RUN_LOG_DIR}" "${RUN_DASHBOARD_DIR}" "$(dirname "${LATEST_HEALTH_FILE}")"

touch "${STEP_RESULT_TSV}"
touch "${PIPELINE_LOG}"
exec > >(tee -a "${PIPELINE_LOG}") 2>&1

START_EPOCH="$(date +%s)"
START_ISO="$(date -Iseconds)"

status="success"
failure_reason=""

log_info() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

has_matching_files() {
  local directory="$1"
  local pattern="$2"
  local path
  shopt -s nullglob
  for path in "${directory}"/${pattern}; do
    if [[ -f "${path}" ]]; then
      shopt -u nullglob
      return 0
    fi
  done
  shopt -u nullglob
  return 1
}

write_step_result() {
  local name="$1"
  local step_status="$2"
  local attempts="$3"
  local duration_sec="$4"
  local log_file="$5"
  local command="$6"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${name}" "${step_status}" "${attempts}" "${duration_sec}" "${log_file}" "${command}" >> "${STEP_RESULT_TSV}"
}

run_step() {
  local name="$1"
  local command="$2"
  local step_log="${RUN_LOG_DIR}/${name}.log"
  local step_start attempt exit_code step_end step_duration
  step_start="$(date +%s)"
  attempt=0
  exit_code=0

  log_info "STEP[${name}] start"
  log_info "STEP[${name}] command: ${command}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    : > "${step_log}"
    write_step_result "${name}" "dry_run" "0" "0" "${step_log}" "${command}"
    log_info "STEP[${name}] dry-run skip"
    return 0
  fi

  while true; do
    attempt=$((attempt + 1))
    echo "---- attempt ${attempt} @ $(date -Iseconds) ----" >> "${step_log}"
    if bash -lc "${command}" >> "${step_log}" 2>&1; then
      exit_code=0
      break
    fi
    exit_code=$?
    if [[ "${attempt}" -gt "${MAX_RETRIES}" ]]; then
      break
    fi
    log_info "STEP[${name}] attempt ${attempt} failed with code ${exit_code}, retry after ${RETRY_DELAY_SEC}s"
    sleep "${RETRY_DELAY_SEC}"
  done

  step_end="$(date +%s)"
  step_duration=$((step_end - step_start))

  if [[ "${exit_code}" -eq 0 ]]; then
    write_step_result "${name}" "success" "${attempt}" "${step_duration}" "${step_log}" "${command}"
    log_info "STEP[${name}] success in ${step_duration}s (attempts=${attempt})"
    return 0
  fi

  write_step_result "${name}" "failed" "${attempt}" "${step_duration}" "${step_log}" "${command}"
  log_info "STEP[${name}] failed in ${step_duration}s (attempts=${attempt}, exit=${exit_code})"
  return "${exit_code}"
}

snapshot_latest_file="${ROOT_DIR}/data/ashare_snapshots/ashare_latest.csv"
run_snapshot_dir="${RUN_DATA_DIR}/ashare_snapshots"
run_candidate_dir="${RUN_DATA_DIR}/candidate_pools"
run_analysis_dir="${RUN_DATA_DIR}/analysis_reports"
run_backtest_dir="${RUN_DATA_DIR}/backtests"
run_risk_dir="${RUN_DATA_DIR}/risk_reports"
run_dashboard_html="${RUN_DASHBOARD_DIR}/index.html"
run_standard_json="${RUN_DATA_DIR}/api/standard_snapshot.json"

mkdir -p "${run_snapshot_dir}" "${run_candidate_dir}" "${run_analysis_dir}" "${run_backtest_dir}" "${run_risk_dir}"

if [[ "${SKIP_SYNC}" == "0" ]]; then
  run_step "sync_snapshot" \
    "cd '${ROOT_DIR}' && '${PYTHON_BIN}' stock_analyzer.py --sync-a-share --runs 1" || {
      status="failed"
      failure_reason="sync_snapshot"
    }
fi

if [[ "${status}" == "success" && -f "${snapshot_latest_file}" && "${DRY_RUN}" == "0" ]]; then
  cp "${snapshot_latest_file}" "${run_snapshot_dir}/ashare_latest.csv"
fi

if [[ "${status}" == "success" && "${SKIP_SCAN}" == "0" && "${DRY_RUN}" == "0" && ! -f "${snapshot_latest_file}" ]]; then
  scan_precheck_log="${RUN_LOG_DIR}/scan_candidates.log"
  : > "${scan_precheck_log}"
  echo "snapshot file not found: ${snapshot_latest_file}" >> "${scan_precheck_log}"
  write_step_result "scan_candidates" "failed_precheck" "0" "0" "${scan_precheck_log}" "snapshot_file_exists"
  log_info "STEP[scan_candidates] precheck failed: snapshot file not found: ${snapshot_latest_file}"
  status="failed"
  failure_reason="scan_candidates_missing_snapshot"
fi

if [[ "${status}" == "success" && "${SKIP_SCAN}" == "0" ]]; then
  run_step "scan_candidates" \
    "cd '${ROOT_DIR}' && '${PYTHON_BIN}' stock_analyzer.py --scan --snapshot-file '${snapshot_latest_file}' --universe '${UNIVERSE}' --top '${TOP_N}' --candidate-output-dir '${run_candidate_dir}'" || {
      status="failed"
      failure_reason="scan_candidates"
    }
  if [[ "${status}" == "success" && "${DRY_RUN}" == "0" ]]; then
    if ! has_matching_files "${run_candidate_dir}" "*.csv"; then
      if [[ "${UNIVERSE}" != "all" ]]; then
        log_info "STEP[scan_candidates] fallback: universe=${UNIVERSE} produced no candidate file, retry with universe=all"
        run_step "scan_candidates_fallback_all" \
          "cd '${ROOT_DIR}' && '${PYTHON_BIN}' stock_analyzer.py --scan --snapshot-file '${snapshot_latest_file}' --universe 'all' --top '${TOP_N}' --candidate-output-dir '${run_candidate_dir}'" || {
            status="failed"
            failure_reason="scan_candidates_fallback_all"
          }
      fi
      if [[ "${status}" == "success" ]]; then
        if ! has_matching_files "${run_candidate_dir}" "*.csv"; then
          log_info "STEP[scan_candidates] warning: no candidate CSV generated in ${run_candidate_dir}"
        fi
      fi
    fi
  fi
fi

if [[ "${status}" == "success" && "${SKIP_ANALYSIS}" == "0" ]]; then
  run_step "analyze_single" \
    "cd '${ROOT_DIR}' && '${PYTHON_BIN}' stock_analyzer.py '${SINGLE_SYMBOL}' --no-llm --analysis-save --analysis-output-dir '${run_analysis_dir}'" || {
      status="failed"
      failure_reason="analyze_single"
    }
  if [[ "${status}" == "success" && "${DRY_RUN}" == "0" ]]; then
    if ! has_matching_files "${run_analysis_dir}" "*.json"; then
      log_info "STEP[analyze_single] failed: no analysis JSON generated in ${run_analysis_dir}"
      status="failed"
      failure_reason="analyze_single_missing_output"
    fi
  fi
fi

if [[ "${status}" == "success" && "${SKIP_PORTFOLIO}" == "0" ]]; then
  run_step "backtest_portfolio" \
    "cd '${ROOT_DIR}' && '${PYTHON_BIN}' stock_analyzer.py --portfolio-symbols '${PORTFOLIO_SYMBOLS}' --backtest --bt-fee-rate '${BT_FEE_RATE}' --bt-slippage-bps '${BT_SLIPPAGE_BPS}' --bt-min-hold-days '${BT_MIN_HOLD_DAYS}' --bt-signal-confirm-days '${BT_SIGNAL_CONFIRM_DAYS}' --bt-max-positions '${BT_MAX_POSITIONS}' --risk-report --bt-save --bt-output-dir '${run_backtest_dir}' --risk-output-dir '${run_risk_dir}'" || {
      status="failed"
      failure_reason="backtest_portfolio"
    }
  if [[ "${status}" == "success" && "${DRY_RUN}" == "0" ]]; then
    if ! has_matching_files "${run_backtest_dir}" "bt_portfolio_*.json"; then
      log_info "STEP[backtest_portfolio] failed: no backtest JSON generated in ${run_backtest_dir}"
      status="failed"
      failure_reason="backtest_missing_output"
    fi
  fi
  if [[ "${status}" == "success" && "${DRY_RUN}" == "0" ]]; then
    if ! has_matching_files "${run_risk_dir}" "risk_portfolio_*.json"; then
      log_info "STEP[backtest_portfolio] failed: no risk JSON generated in ${run_risk_dir}"
      status="failed"
      failure_reason="risk_missing_output"
    fi
  fi
fi

if [[ "${status}" == "success" && "${SKIP_DASHBOARD}" == "0" ]]; then
  run_step "build_dashboard" \
    "cd '${ROOT_DIR}' && '${PYTHON_BIN}' -m dashboard.app --data-dir '${RUN_DATA_DIR}' --output '${run_dashboard_html}'" || {
      status="failed"
      failure_reason="build_dashboard"
    }
fi

if [[ "${status}" == "success" ]]; then
  run_step "export_standard_json" \
    "cd '${ROOT_DIR}' && '${PYTHON_BIN}' stock_analyzer.py --standard-json-export --standard-json-data-dir '${RUN_DATA_DIR}' --standard-json-output '${run_standard_json}'" || {
      status="failed"
      failure_reason="export_standard_json"
    }
  if [[ "${status}" == "success" && "${DRY_RUN}" == "0" ]]; then
    if [[ ! -f "${run_standard_json}" ]]; then
      log_info "STEP[export_standard_json] failed: no standard JSON generated at ${run_standard_json}"
      status="failed"
      failure_reason="standard_json_missing_output"
    fi
  fi
fi

END_EPOCH="$(date +%s)"
END_ISO="$(date -Iseconds)"
DURATION_SEC=$((END_EPOCH - START_EPOCH))

"${PYTHON_BIN}" - "${STEP_RESULT_TSV}" "${HEALTH_FILE}" "${RUN_ID}" "${RUN_DATE}" "${START_ISO}" "${END_ISO}" "${DURATION_SEC}" "${status}" "${failure_reason}" "${ROOT_DIR}" "${PYTHON_BIN}" "${RUN_DIR}" "${RUN_DATA_DIR}" "${run_dashboard_html}" "${run_standard_json}" <<'PY'
import json
import sys
from pathlib import Path

(
    step_tsv,
    health_path,
    run_id,
    run_date,
    started_at,
    ended_at,
    duration_sec,
    status,
    failure_reason,
    workspace,
    python_bin,
    run_dir,
    run_data_dir,
    dashboard_html,
    standard_json,
) = sys.argv[1:]

steps = []
step_file = Path(step_tsv)
if step_file.exists():
    for line in step_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, step_status, attempts, duration, log_file, command = line.split("\t", 5)
        steps.append(
            {
                "name": name,
                "status": step_status,
                "attempts": int(attempts),
                "duration_sec": int(duration),
                "log_file": log_file,
                "command": command,
            }
        )

payload = {
    "run_id": run_id,
    "run_date": run_date,
    "started_at": started_at,
    "ended_at": ended_at,
    "duration_sec": int(duration_sec),
    "status": status,
    "failure_reason": failure_reason or None,
    "workspace": workspace,
    "python_bin": python_bin,
    "steps": steps,
    "artifacts": {
        "run_dir": run_dir,
        "data_dir": run_data_dir,
        "dashboard_html": dashboard_html if Path(dashboard_html).exists() else None,
        "standard_json": standard_json if Path(standard_json).exists() else None,
    },
}

Path(health_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY

cp "${HEALTH_FILE}" "${LATEST_HEALTH_FILE}"

log_info "Pipeline finished: status=${status}, duration=${DURATION_SEC}s"
log_info "Health file: ${HEALTH_FILE}"
log_info "Latest health: ${LATEST_HEALTH_FILE}"

if [[ "${status}" != "success" ]]; then
  exit 1
fi

exit 0
