import os

from .defaults import *

# Production security settings
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')

# Trust nginx's X-Forwarded-Proto header so request.is_secure() works correctly
# behind the SSL-terminating reverse proxy. Required for correct CSRF behaviour.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Remove development-only middleware
MIDDLEWARE = [m for m in MIDDLEWARE if m != 'django_browser_reload.middleware.BrowserReloadMiddleware']

# Static and media files
STATIC_ROOT = os.getenv('DJANGO_STATIC_ROOT', '/app/static')
MEDIA_ROOT = os.getenv('DJANGO_MEDIA_ROOT', '/app/media')

# ── Database connection pooling ───────────────────────────────────────────────
# Reuse DB connections across requests instead of opening a new TCP connection
# on every request. CONN_HEALTH_CHECKS avoids stale-connection errors with
# gthread workers. SSL disabled because Postgres is on the same Docker network.
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = "disable"

# ── Cache — database-backed so all Gunicorn workers share the same cache.
# LocMemCache is per-process; with multiple workers the OTP written by worker A
# is invisible to worker B, breaking the password-reset flow.
# DatabaseCache uses the same PostgreSQL instance all workers already connect to.
# Run once to create the table:
#   python manage.py createcachetable
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
