#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./run_local.sh <match_id> [model] [language] [window_ms] [--silent]
#
# Example:
#   ./run_local.sh 12345 llama3.2:latest no 1200
#   ./run_local.sh 12345 llama3.2:latest en 1000 --silent

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <match_id> [model] [language] [window_ms] [--silent]"
  exit 1
fi

MATCH_ID="$1"
MODEL="${2:-llama3.2:latest}"
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

if ! command -v ollama >/dev/null 2>&1; then
  echo "[error] ollama not found. Install from https://ollama.com/"
  exit 1
fi

echo "[setup] Syncing Python dependencies..."
uv sync

# Start Ollama server if not already running
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "[setup] Ollama server not detected. Starting ollama serve..."
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  sleep 2
fi

# Wait for Ollama server
for i in {1..20}; do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "[error] Ollama server did not start. See /tmp/ollama-serve.log"
  exit 1
fi

echo "[setup] Ensuring model is available: ${MODEL}"
if ! ollama show "${MODEL}" >/dev/null 2>&1; then
  ollama pull "${MODEL}"
fi

# Optional sanity check: can Python llm resolve the model?
echo "[setup] Verifying llm model resolution..."
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
