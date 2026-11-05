"""Small helpers shared by the OCR views."""
from django.http import JsonResponse

from ....security.permissions import has_matrix_perm
from ....utils.pos import ocr_cache


def _int_or_none(v, lo=None, hi=None):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if lo is not None and n < lo:
        return None
    if hi is not None and n > hi:
        return None
    return n


def _too_many(request, bucket, limit):
    if ocr_cache.rate_ok(request.user.id, bucket, limit):
        return None
    return JsonResponse({'success': False, 'message': 'Too many scans. Wait a few seconds.'}, status=429)


def _has_perm(user, key):
    try:
        return bool(has_matrix_perm(user, key))
    except Exception:
        return bool(user.is_superuser)
