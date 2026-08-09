from .defaults import *


ALLOWED_HOSTS = ['*', 'localhost', '127.0.0']

# GZip compression for local dev (Nginx handles this in production)
MIDDLEWARE = ['django.middleware.gzip.GZipMiddleware'] + MIDDLEWARE


STATIC_ROOT = BASE_DIR / 'static'
MEDIA_ROOT = BASE_DIR / 'media'

# Keep DB connections alive across requests (avoids reconnect overhead per request)
DATABASES['default']['CONN_MAX_AGE'] = 60

# In-memory cache for local dev (speeds up sessions + context processor caching)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'

