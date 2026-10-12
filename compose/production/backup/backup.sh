#!/bin/bash
set -eo pipefail

DATE=$(date +'%Y-%m-%d_%H%M%S')
HUMAN_DATE=$(date +'%Y-%m-%d %H:%M:%S UTC')
BACKUP_DIR="/backups"
BACKUP_FILE="${BACKUP_DIR}/trustbuilding_db_${DATE}.sql.gz"
START_TIME=$(date +%s)

mkdir -p "${BACKUP_DIR}"

BOT_TOKEN="${TELEGRAM_BACKUP_BOT_TOKEN:-${TELEGRAM_BOT_TOKEN:-}}"

send_telegram_alert() {
    local message="$1"
    if [ -n "${BOT_TOKEN}" ] && [ -n "${TELEGRAM_BACKUP_CHAT_ID:-}" ]; then
        local thread_param=""
        if [ -n "${TELEGRAM_BACKUP_THREAD_ID:-}" ]; then
            thread_param="-F message_thread_id=${TELEGRAM_BACKUP_THREAD_ID}"
        fi
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -F "chat_id=${TELEGRAM_BACKUP_CHAT_ID}" \
            ${thread_param} \
            -F "parse_mode=HTML" \
            -F "text=${message}" > /dev/null || true
    fi
}

echo "[$(date)] Starting PostgreSQL database backup for ${POSTGRES_DB}..."

# Export password for pg_dump
export PGPASSWORD="${POSTGRES_PASSWORD}"

# Execute pg_dump and compress
if ! pg_dump -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip -9 > "${BACKUP_FILE}"; then
    echo "[$(date)] ERROR: pg_dump failed!"
    send_telegram_alert "🔴 <b>CRITICAL: TrustBuilding DB Backup FAILED!</b>
📅 <b>Time:</b> ${HUMAN_DATE}
⚠️ <b>Error:</b> pg_dump execution error."
    rm -f "${BACKUP_FILE}"
    exit 1
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
FILE_BYTES=$(stat -c%s "${BACKUP_FILE}")

echo "[$(date)] Backup completed successfully in ${DURATION}s. Size: ${FILE_SIZE} (${FILE_BYTES} bytes)"

# Upload to Telegram if credentials are provided
if [ -n "${BOT_TOKEN}" ] && [ -n "${TELEGRAM_BACKUP_CHAT_ID:-}" ]; then
    echo "[$(date)] Uploading backup to Telegram..."
    
    # Check if file exceeds Telegram Bot API 50MB limit (52428800 bytes)
    if [ "${FILE_BYTES}" -ge 50000000 ]; then
        echo "[$(date)] WARNING: Backup file exceeds 50MB limit. Splitting into chunks..."
        split -b 45M "${BACKUP_FILE}" "${BACKUP_FILE}.part_"
        
        send_telegram_alert "⚠️ <b>TrustBuilding DB Backup: File exceeds 50MB</b>
📅 <b>Date:</b> ${HUMAN_DATE}
📦 <b>Total Size:</b> ${FILE_SIZE}
Uploading in multiple parts..."
        
        for part in "${BACKUP_FILE}.part_"*; do
            local_thread_param=""
            if [ -n "${TELEGRAM_BACKUP_THREAD_ID:-}" ]; then
                local_thread_param="-F message_thread_id=${TELEGRAM_BACKUP_THREAD_ID}"
            fi
            curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" \
                -F "chat_id=${TELEGRAM_BACKUP_CHAT_ID}" \
                ${local_thread_param} \
                -F "document=@${part}" \
                -F "caption=📦 Part: $(basename "${part}")" > /dev/null || true
            rm -f "${part}"
        done
    else
        CAPTION="🟢 <b>TrustBuilding Database Backup</b>
📅 <b>Date:</b> ${HUMAN_DATE}
📦 <b>Size:</b> ${FILE_SIZE}
⏱ <b>Duration:</b> ${DURATION}s
🗄 <b>Database:</b> PostgreSQL 18
📁 <b>File:</b> $(basename "${BACKUP_FILE}")"
        
        thread_param=""
        if [ -n "${TELEGRAM_BACKUP_THREAD_ID:-}" ]; then
            thread_param="-F message_thread_id=${TELEGRAM_BACKUP_THREAD_ID}"
        fi
        
        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument" \
            -F "chat_id=${TELEGRAM_BACKUP_CHAT_ID}" \
            ${thread_param} \
            -F "document=@${BACKUP_FILE}" \
            -F "parse_mode=HTML" \
            -F "caption=${CAPTION}")
            
        HTTP_STATUS=$(echo "${RESPONSE}" | tail -n1)
        if [ "${HTTP_STATUS}" != "200" ]; then
            echo "[$(date)] ERROR: Failed to upload document to Telegram! HTTP Status: ${HTTP_STATUS}"
            send_telegram_alert "🔴 <b>TrustBuilding DB Backup: Telegram upload failed!</b>%0AHTTP Status: ${HTTP_STATUS}"
        else
            echo "[$(date)] Successfully sent backup to Telegram!"
        fi
    fi
else
    echo "[$(date)] Telegram credentials not configured. Skipping Telegram upload."
fi

# Retention policy: Prune local backups older than BACKUP_KEEP_DAYS (default: 7 days)
KEEP_DAYS="${BACKUP_KEEP_DAYS:-7}"
echo "[$(date)] Pruning local backups older than ${KEEP_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "trustbuilding_db_*.sql.gz" -mtime +"${KEEP_DAYS}" -delete

echo "[$(date)] Backup process finished successfully."
