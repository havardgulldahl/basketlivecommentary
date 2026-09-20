#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./run_local.sh <match_id> [model] [language] [window_ms] [--silent]
#
# Example:
#   ./run_local.sh 12345 qwen2-1_5b-instruct-q4_0 no 1200
#   ./run_local.sh 12345 qwen2-1_5b-instruct-q4_0 en 1000 --silent

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <match_id> [model] [language] [window_ms] [--silent]"
  exit 1
fi

MATCH_ID="$1"
MODEL="${2:-qwen2-1_5b-instruct-q4_0}"
LANGUAGE="${3:-no}"
WINDOW_MS="${4:-1200}"
SILENT_FLAG="${5:-}"

if [[ "$LANGUAGE" != "no" && "$LANGUAGE" != "en" ]]; then
  echo "[error] language must be 'no' or 'en'"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[error] uv not found. Install from https://docs.astral.sh/uv/"
  exit 1
fi

if ! command -v llm >/dev/null 2>&1; then
  echo "[error] llm not found. Install with: uv tool install llm"
  exit 1
fi

echo "[setup] Syncing Python dependencies..."
uv sync

# Verify the Python API can resolve the configured model or alias.
echo "[setup] Verifying Datasette llm model resolution..."
MODEL_TO_CHECK="${MODEL}" uv run python - <<'PY'
import os
import sys
try:
    import llm
    model_id = os.environ["MODEL_TO_CHECK"]
    m = llm.get_model(model_id)
    print(f"[ok] llm resolved model: {m.model_id}")
except Exception as e:
    print(f"[error] llm could not resolve model: {e}")
    sys.exit(1)
PY

echo "[run] Starting commentary app..."
CMD=(uv run python src/main.py "$MATCH_ID" --use-llm --llm-model "$MODEL" --llm-window-ms "$WINDOW_MS" --language "$LANGUAGE")

if [[ "$SILENT_FLAG" == "--silent" ]]; then
  CMD+=(--silent)
fi

echo "[run] ${CMD[*]}"
exec "${CMD[@]}"
