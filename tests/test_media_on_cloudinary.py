# tests/test_media_on_cloudinary.py
from django.apps import apps
from django.db import models
from django.utils.functional import empty


def test_every_file_field_uses_cloudinary():
    bad = []
    for model in apps.get_models():
        for f in model._meta.get_fields():
            if isinstance(f, models.FileField):
                st = f.storage
                if hasattr(st, "_wrapped"):
                    if st._wrapped is empty:
                        st._setup()
                    st = st._wrapped
                if "cloudinary_storage" not in type(st).__module__:
                    bad.append(f"{model.__name__}.{f.name} -> {type(st).__name__}")
    assert not bad, bad
