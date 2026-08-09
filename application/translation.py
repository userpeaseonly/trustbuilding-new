"""
Translation registry for django-modeltranslation.

This module registers models that need multi-language support (uz, ru, en).
When adding a new translatable model:
1. Import the model
2. Create a TranslationOptions class with `fields` tuple listing translatable fields
3. Register: translator.register(YourModel, YourModelTranslationOptions)
4. Run: python manage.py makemigrations && python manage.py migrate

Example:
    from modeltranslation.translator import translator, TranslationOptions
    from yourapp.models import YourModel
    
    class YourModelTranslationOptions(TranslationOptions):
        fields = ('title', 'description')
    
    translator.register(YourModel, YourModelTranslationOptions)
"""
from modeltranslation.translator import translator, TranslationOptions

# Add modeltranslation registrations here for TrustBuilding models
