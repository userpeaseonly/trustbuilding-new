# --- Stage 1: Build dependencies ---
FROM python:3.13-slim as builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  libpq-dev \
  gettext \
  curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# --- Stage 2: Run application ---
FROM python:3.13-slim as application

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install runtime dependencies (gettext for compilemessages, Node.js for Tailwind)
RUN apt-get update && apt-get install -y --no-install-recommends \
  libpq-dev \
  gettext \
  curl \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && node --version \
  && npm --version \
  && apt-get purge -y --auto-remove curl -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH"

# Copy installed python dependencies
COPY --from=builder /opt/venv /opt/venv

# Copy entrypoint and start scripts
COPY ./compose/staging/django/entrypoint /entrypoint
COPY ./compose/staging/django/start /start
RUN sed -i 's/\r$//g' /entrypoint /start \
  && chmod +x /entrypoint /start

# Copy the Django application from the context
COPY . .

# Use the start script as the entrypoint
ENTRYPOINT ["/entrypoint"]
