#!/usr/bin/env bash
# scripts/ci/serve_until.sh <minutes>  -- keep job alive, exit early if a newer run is queued
set -uo pipefail
END=$(( $(date +%s) + $1 * 60 ))
while [ "$(date +%s)" -lt "$END" ]; do
  NEWER=$(gh api "repos/$GITHUB_REPOSITORY/actions/runs?branch=$GITHUB_REF_NAME&per_page=5" \
          --jq "[.workflow_runs[] | select(.id > $GITHUB_RUN_ID)] | length" 2>/dev/null || echo 0)
  if [ "${NEWER:-0}" -gt 0 ]; then echo "STOP=true" >> "$GITHUB_ENV"; echo "Newer run detected; handing over."; exit 0; fi
  sleep 30
done
