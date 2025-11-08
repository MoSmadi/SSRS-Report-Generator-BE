#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC2046
  source "$ENV_FILE"
  set +a
fi

cd "$SCRIPT_DIR"
exec python3 smoke_check.py
