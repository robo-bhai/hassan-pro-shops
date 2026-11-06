from django.conf import settings

# Sirf in paths par embed allow hoga (baaki site protected rahegi)
EMBED_PREFIXES = ("/shop", "/store", "/stores", "/cart", "/checkout", "/product", "/track", "/account", "/auth", "/vendor", "/media", "/static")

class AllowAppFraming:
    def __init__(self, get_response):
        self.get_response = get_response
        self.ancestors = " ".join(
            ["'self'"] + getattr(settings, "FRAME_ANCESTORS", [])
        )

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(EMBED_PREFIXES):
            response.xframe_options_exempt = True          # X-Frame-Options hat jata hai
            response["Content-Security-Policy"] = f"frame-ancestors {self.ancestors}"
        return response
