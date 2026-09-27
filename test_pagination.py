import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings")
django.setup()

from application.pagination import encode_cursor, decode_cursor
print(encode_cursor(5))
print(decode_cursor(encode_cursor(5)))
