#!/bin/bash
# =============================================================================
# setup_cron.sh — Add Imaan monthly student charge job to the server crontab
#
# Usage:
#   chmod +x setup_cron.sh
#   ./setup_cron.sh
#
# What it does:
#   Adds a cron job to run "charge_students_monthly" at 00:01 on the 1st of
#   every month, writing output to /var/log/imaan_charge.log
#
# Prerequisites:
#   - Docker and docker compose must be installed on the server
#   - The imaan project must be at /home/imaan/imaan (adjust COMPOSE_DIR below)
#   - The web container must be running (started by another service/cron/systemd)
# =============================================================================

set -e

# ── Configuration ─────────────────────────────────────────────────────────────
COMPOSE_DIR="${IMAAN_DIR:-/home/imaan/imaan}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
LOG_FILE="${LOG_FILE:-/var/log/imaan_charge.log}"

# The cron expression: 1 minute past midnight on the 1st of every month
CRON_SCHEDULE="1 0 1 * *"
CRON_CMD="cd $COMPOSE_DIR && docker compose -f $COMPOSE_FILE exec -T web python manage.py charge_students_monthly >> $LOG_FILE 2>&1"
CRON_ENTRY="$CRON_SCHEDULE $CRON_CMD"
CRON_MARKER="# imaan-monthly-charge"

# ── Install ───────────────────────────────────────────────────────────────────
echo "Installing monthly charge cron job..."
echo "  Schedule : $CRON_SCHEDULE (00:01 on the 1st of every month)"
echo "  Command  : $CRON_CMD"
echo "  Log      : $LOG_FILE"
echo ""

# Check if the job is already installed
if crontab -l 2>/dev/null | grep -q "$CRON_MARKER"; then
    echo "⚠  Cron job already present. Skipping."
else
    # Add to crontab (preserving existing jobs)
    (crontab -l 2>/dev/null || true; echo "$CRON_ENTRY $CRON_MARKER") | crontab -
    echo "✅ Cron job installed successfully."
fi

echo ""
echo "Current crontab:"
crontab -l

# ── How to remove ─────────────────────────────────────────────────────────────
echo ""
echo "To remove this job later, run:"
echo "  crontab -l | grep -v '$CRON_MARKER' | crontab -"
