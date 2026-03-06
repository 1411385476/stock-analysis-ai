#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/wgj/openclaw-finance"
PIPELINE_SCRIPT="${ROOT_DIR}/scripts/run_daily_pipeline.sh"
PYTHON_BIN="${ROOT_DIR}/venv312/bin/python"
HEALTH_FILE="${ROOT_DIR}/data/pipeline_runs/latest_health.json"

if [[ ! -x "${PIPELINE_SCRIPT}" ]]; then
  echo "[E_INPUT] pipeline script not executable: ${PIPELINE_SCRIPT}"
  exit 2
fi

set +e
bash "${PIPELINE_SCRIPT}" "$@"
PIPE_STATUS=$?
set -e

if [[ ! -f "${HEALTH_FILE}" ]]; then
  echo "Pipeline 执行结果"
  echo "status: failed"
  echo "failure_reason: latest_health_missing"
  echo "run_dir: null"
  echo "dashboard_html: null"
  exit "${PIPE_STATUS}"
fi

"${PYTHON_BIN}" - "${HEALTH_FILE}" <<'PY'
import json
import sys
from pathlib import Path

health_path = Path(sys.argv[1])
try:
    payload = json.loads(health_path.read_text(encoding="utf-8"))
except Exception:
    print("Pipeline 执行结果")
    print("status: failed")
    print("failure_reason: latest_health_parse_error")
    print("run_dir: null")
    print("dashboard_html: null")
    sys.exit(0)

status = payload.get("status", "failed")
failure_reason = payload.get("failure_reason")
artifacts = payload.get("artifacts") or {}
run_dir = artifacts.get("run_dir")
dashboard_html = artifacts.get("dashboard_html")

print("Pipeline 执行结果")
print(f"status: {status}")
print(f"failure_reason: {failure_reason if failure_reason is not None else 'null'}")
print(f"run_dir: {run_dir if run_dir else 'null'}")
print(f"dashboard_html: {dashboard_html if dashboard_html else 'null'}")

if status != "success" and run_dir:
    print(f"建议查看: {run_dir}/pipeline.log")
elif status == "success" and dashboard_html:
    print("可直接打开 dashboard_html 查看结果。")
PY

exit "${PIPE_STATUS}"
