"""Checkout ke liye cart: Buy Now mode mein sirf wahi ek product, warna normal cart."""


def get_checkout_cart(request):
    """Buy Now mode mein sirf wahi ek product (customer ki asli cart mehfooz rehti hai);
    warna normal cart."""
    if request.session.get('buy_now_mode'):
        item = request.session.get('buy_now_item')
        if item:
            return item
        request.session.pop('buy_now_mode', None)
        request.session.pop('buy_now_product_id', None)
        request.session.modified = True
    return request.session.get('cart', {})
