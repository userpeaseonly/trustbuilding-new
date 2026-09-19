# Compile CSS once, using the locked frontend dependencies.
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/theme/static_src
COPY theme/static_src/package.json theme/static_src/package-lock.json ./
RUN npm ci --no-audit --no-fund
WORKDIR /app
# Tailwind scans templates and Python across the project.
COPY . .
RUN cd theme/static_src && npm run build

FROM python:3.13-slim-bookworm AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

FROM python:3.13-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_ENV=production \
    DJANGO_SETTINGS_MODULE=application.settings.production \
    PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 gettext \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 trustbuilding \
    && useradd --uid 10001 --gid trustbuilding --create-home trustbuilding
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY . .
COPY --from=frontend /app/theme/static/css/dist /app/theme/static/css/dist
COPY compose/production/django/entrypoint /entrypoint
COPY compose/production/django/start /start
# Compile translations without loading Django settings or needing build secrets.
RUN python -c "from pathlib import Path; import subprocess; [subprocess.run(['msgfmt', '--check', '-o', str(p.with_suffix('.mo')), str(p)], check=True) for p in Path('locale').rglob('*.po')]" \
    && sed -i 's/\r$//g' /entrypoint /start \
    && chmod +x /entrypoint /start \
    && mkdir -p /app/static /app/media /var/lib/celery \
    && chown trustbuilding:trustbuilding /app/static /app/media /var/lib/celery
USER trustbuilding
EXPOSE 8000
ENTRYPOINT ["/entrypoint"]
CMD ["/start"]
