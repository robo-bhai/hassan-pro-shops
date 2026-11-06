# app/storage.py  -- for non-image FileFields (PDF, DOCX, ZIP ...)
def raw_media_storage():
    from cloudinary_storage.storage import RawMediaCloudinaryStorage
    return RawMediaCloudinaryStorage()

# usage in models:  agreement_file = models.FileField(upload_to="loan_agreements/", storage=raw_media_storage, null=True, blank=True)
# This produces state-only AlterField migrations; no table data changes.
