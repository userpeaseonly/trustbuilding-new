from django.utils.text import slugify

from slugify import slugify as slug_translate

import re, string, random
import os
from django.core.exceptions import ValidationError

def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, title, new_slug=None):
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(title, allow_unicode=True)
        slug = slug_translate(slug)
    title = ''.join(re.split(r'[‘.;!?,\']', title))
    Klass = instance.__class__
    max_length = Klass._meta.get_field('slug').max_length
    slug = slug[:max_length]
    qs_exists = Klass.objects.filter(slug=slug).exists()

    if qs_exists:
        new_slug = "{slug}-{randstr}".format(
            slug=slug[:max_length - 5], randstr=random_string_generator(size=4))

        return unique_slug_generator(instance, title, new_slug=new_slug)
    return slug


def validate_audio_extension(value):
    allowed_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.aiff', '.m4a']
    ext = os.path.splitext(value.name)[1]
    if not ext.lower() in allowed_extensions:
        raise ValidationError('Only MP3, WAV, FLAC, AAC, OGG, AIFF, M4A files allowed.')


def validate_video_extension(value):
    allowed_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']
    ext = os.path.splitext(value.name)[1]
    if not ext.lower() in allowed_extensions:
        raise ValidationError('Only MP4, AVI, MKV, MOV, WMV, FLV, WEBM files allowed.')


def validate_book_extension(value):
    allowed_extensions = ['.epub', '.pdf', '.mobi', '.azw', '.azw3', '.docx']
    ext = os.path.splitext(value.name)[1]
    if not ext.lower() in allowed_extensions:
        raise ValidationError('Only Epub, Pdf, Mobi, Azw, Azw3, Docx files allowed.')


def validate_image_extension(value):
    allowed_extensions = ['.jpg', '.png', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.tiff',]
    ext = os.path.splitext(value.name)[1]
    if not ext.lower() in allowed_extensions:
        raise ValidationError('Only jpg, png, jpeg, gif, svg, webp, bmp, tiff files allowed.')


def upload_to_audio(instance, filename):
    return f'audios/{instance.book_name_id}{filename}'


def upload_to_video(instance, filename):
    return f'videos/{instance.book_name_id}{filename}'