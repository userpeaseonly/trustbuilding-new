import os

from .defaults import *

# Production security settings
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', 'localhost').split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]

# Trust nginx's X-Forwarded-Proto header so request.is_secure() works correctly
# behind the SSL-terminating reverse proxy. Required for correct CSRF behaviour.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Set to 0 only while bootstrapping HTTP, then 1 after Certbot installs HTTPS.
HTTPS_ENABLED = os.getenv('DJANGO_HTTPS_ENABLED', '1') == '1'
SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SECURE_REDIRECT_EXEMPT = [r'^health/$']
# Enable HSTS only after HTTPS and certificate renewal have been verified.
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0'))

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
# The web startup script creates the cache table before serving requests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
