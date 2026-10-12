FROM postgres:18-bookworm

# Install curl, cron, and ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    cron \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY compose/production/backup/backup.sh /app/backup.sh
COPY compose/production/backup/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/backup.sh /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
