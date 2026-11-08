"""Shop ke payment options.

COD hamesha maujood hai. JazzCash / EasyPaisa tab nazar aate hain jab company settings
mein un ka number likha ho (CompanyInfo.jazzcash_number / easypaisa_number).
Koi online gateway nahi: customer us number par khud payment bhejta hai.
"""
from ..models import CompanyInfo


def get_payment_options():
    """Returns (methods, numbers).
    methods = [(value, label, description), ...]   numbers = {'jazzcash': '03..', ...}"""
    company = CompanyInfo.objects.first()
    methods = [('cod', '💵 Cash on Delivery', 'Ghar par cash dein')]
    numbers = {}

    jazz = ((getattr(company, 'jazzcash_number', '') or '').strip()) if company else ''
    easy = ((getattr(company, 'easypaisa_number', '') or '').strip()) if company else ''

    if jazz:
        methods.append(('jazzcash', '📱 JazzCash', 'Company ke JazzCash number par payment bhejein'))
        numbers['jazzcash'] = jazz
    if easy:
        methods.append(('easypaisa', '📱 EasyPaisa', 'Company ke EasyPaisa number par payment bhejein'))
        numbers['easypaisa'] = easy
    return methods, numbers


def clean_payment_method(value):
    """Sirf wohi method manzoor jo abhi available ho; warna 'cod'."""
    methods, _ = get_payment_options()
    return value if value in [m[0] for m in methods] else 'cod'
