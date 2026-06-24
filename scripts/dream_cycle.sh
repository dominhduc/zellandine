#!/usr/bin/env bash
# Dream cycle entry point — called by Hermes cron scheduler.
# Runs the full 5-stage cycle and outputs a summary to stdout.
#
# Usage in cron:
#   script: dream_cycle.sh
#   no_agent: true
#   deliver: local
set -euo pipefail

ZELLANDINE_HOME="${ZELLANDINE_HOME:-$HOME/.hermes/zellandine}"
ARTIFACT_ROOT="$ZELLANDINE_HOME/artifacts"
CONFIG_FILE="$ZELLANDINE_HOME/config.yaml"

# Run the dream cycle
python -m zellandine run \
  --depth "${DREAM_DEPTH:-full}" \
  --sessions "${DREAM_SESSIONS:-14}" \
  ${DREAM_DRY_RUN:+--dry-run} \
  --artifact-root "$ARTIFACT_ROOT" \
  2>&1 || true

# Output last run status for cron delivery
if [ -f "$ARTIFACT_ROOT/latest_status.txt" ]; then
  cat "$ARTIFACT_ROOT/latest_status.txt"
fi
