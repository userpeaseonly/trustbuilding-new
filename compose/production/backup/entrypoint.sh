#!/bin/bash
set -euo pipefail

# If a specific command was passed to container, run it directly
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "[$(date)] Initializing TrustBuilding Database Backup Service..."

# Ensure /backups directory exists
mkdir -p /backups

# Export container environment variables for cron execution (properly quoted)
export -p | grep -E ' (POSTGRES_|TELEGRAM_|BACKUP_KEEP_DAYS)' > /app/env.sh
chmod +x /app/env.sh

# Configure cron schedule (default: 03:00 UTC daily)
CRON_SCHEDULE="${BACKUP_CRON:-0 3 * * *}"
echo "[$(date)] Setting backup schedule to: '${CRON_SCHEDULE}'"

# Create crontab file
CRON_FILE="/etc/cron.d/backup-cron"
cat <<EOF > "${CRON_FILE}"
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

${CRON_SCHEDULE} root . /app/env.sh && /app/backup.sh >> /proc/1/fd/1 2>&1
# An empty line is required at the end of this file for a valid cron file
EOF

chmod 0644 "${CRON_FILE}"

echo "[$(date)] Cron daemon starting in foreground. Waiting for scheduled runs..."
exec cron -f
