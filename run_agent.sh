#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_agent.sh  –  Wrapper for daily cron execution of the NewsAgent
#
# Designed to be called by cron:
#   0 7 * * 1-5  /path/to/NewsAgent/run_agent.sh >> /path/to/NewsAgent/cron.log 2>&1
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Resolve the project root (directory containing this script) ───────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Activate virtual environment if present ───────────────────────────────────
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
elif [[ -f "venv/bin/activate" ]]; then
    source venv/bin/activate
fi

# ── Load .env if present ──────────────────────────────────────────────────────
if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# ── Require API key ───────────────────────────────────────────────────────────
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "[ERROR] ANTHROPIC_API_KEY is not set. Exiting." >&2
    exit 1
fi

# ── Run the agent ─────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  NewsAgent run  —  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "════════════════════════════════════════════════════════════"
echo ""

python3 news_agent.py --save "$@"

EXIT_CODE=$?
echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')]  NewsAgent finished with exit code $EXIT_CODE"
exit $EXIT_CODE
