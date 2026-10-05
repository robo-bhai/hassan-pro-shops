# middleware.py - Complete Updated File

from django.shortcuts import redirect
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)


class MultiTenantMiddleware:
    """
    Multi-Tenant Middleware — Subdomain + User-based detection
    
    Priority:
    1. Superuser → bypass (no tenant)
    2. Regular user (client) → tenant from user mapping
    3. Subdomain → tenant from subdomain
    4. Custom domain → tenant from custom domain
    """

    def __init__(self, get_response):
        self.get_response = get_response

        self.skip_urls = [
            '/admin/',
            '/static/',
            '/media/',
            '/subscription/',
            '/login/',
            '/logout/',
            '/register/',
        ]

        self.module_urls = {
            'hr': '/hr/',
            'production': '/production/',
            'supply_chain': '/supply-chain/',
            'installment': '/installments/',
            'shop_portal': '/shop/',
            'ai': '/ai/',
            'accounts': '/accounts/',
            'backup': '/database-backup/',
        }

    def __call__(self, request):
        request.tenant = None
        request.modules = {}
        request.is_super_admin = False

        host = request.get_host().split(':')[0]

        # ========================================== #
        # 1. SKIP URLs (FIRST - sabse pehle)         #
        # ========================================== #
        for url in self.skip_urls:
            if request.path.startswith(url):
                # Skip URLs ke liye bhi tenant detect karo (agar user logged in)
                if request.user.is_authenticated and not request.user.is_superuser:
                    client = self.get_client_from_user(request.user)
                    if client:
                        request.tenant = client
                        request.modules = client.get_modules()
                return self.get_response(request)

        # ========================================== #
        # 2. SUPER ADMIN DOMAINS                     #
        # ========================================== #
        if host in ['uqn88store.com', 'www.uqn88store.com', 'localhost', '127.0.0.1']:
            
            # ✅ Superuser → bypass (no tenant, all access)
            if request.user.is_authenticated and request.user.is_superuser:
                request.is_super_admin = True
                return self.get_response(request)
            
            # ✅ Regular user (client) → user se tenant detect karo
            if request.user.is_authenticated:
                client = self.get_client_from_user(request.user)
                
                if client:
                    request.tenant = client
                    request.modules = client.get_modules()
                    
                    request.session['tenant_id'] = client.id
                    request.session['tenant_name'] = client.business_name
                    request.session['tenant_subdomain'] = client.subdomain
                    
                    # Check subscription expiry
                    if client.is_expired():
                        allowed_paths = ['/subscription/expired/', '/logout/']
                        if request.path not in allowed_paths:
                            return redirect('subscription_expired')
                    
                    # Check module access
                    module_check = self.check_module_access(request)
                    if module_check:
                        return module_check
            
            return self.get_response(request)

        # ========================================== #
        # 3. SUBDOMAIN/CUSTOM DOMAIN BASED TENANT    #
        # ========================================== #
        tenant = self.get_tenant(host)

        if tenant:
            request.tenant = tenant
            request.modules = tenant.get_modules()

            request.session['tenant_id'] = tenant.id
            request.session['tenant_name'] = tenant.business_name
            request.session['tenant_subdomain'] = tenant.subdomain

            # Check subscription expiry
            if tenant.is_expired():
                allowed_paths = ['/subscription/expired/', '/logout/']
                if request.path not in allowed_paths:
                    return redirect('subscription_expired')

            # Check module access
            module_check = self.check_module_access(request)
            if module_check:
                return module_check

        return self.get_response(request)

    # ========================================== #
    # HELPER: Get Client from User               #
    # ========================================== #
    def get_client_from_user(self, user):
        """
        User se Client (tenant) detect karo
        
        Priority:
        1. User.client_profile (OneToOne field)
        2. Client.user (ForeignKey)
        3. User's email se Client match
        4. User.username == Client.subdomain match
        """
        from .models import Client
        
        try:
            # ✅ Method 1: user.client_profile
            if hasattr(user, 'client_profile'):
                if user.client_profile:
                    return user.client_profile
            
            # ✅ Method 2: Client.user (ForeignKey)
            client = Client.objects.filter(user=user).first()
            if client:
                return client
            
            # ✅ Method 3: Email match
            if user.email:
                client = Client.objects.filter(email=user.email).first()
                if client:
                    return client
            
            # ✅ Method 4: Username == Subdomain match (fallback)
            client = Client.objects.filter(subdomain=user.username.lower()).first()
            if client:
                return client
        
        except Exception as e:
            logger.error(f"Client detection error for user {user.username}: {e}")
        
        return None

    # ========================================== #
    # HELPER: Get Tenant from Host               #
    # ========================================== #
    def get_tenant(self, host):
        """Host se Tenant (Client) detect karo"""
        from .models import Client

        # ✅ Custom domain check
        client = Client.objects.filter(
            custom_domain=host,
            subscription_status__in=['active', 'trial']
        ).first()

        if client:
            return client

        # ✅ Subdomain check
        parts = host.split('.')
        if len(parts) >= 2:
            subdomain = parts[0].lower()

            # Skip reserved subdomains
            if subdomain in ['www', 'admin', 'api', 'app', 'mail', 'ftp']:
                return None

            try:
                client = Client.objects.get(
                    subdomain=subdomain,
                    subscription_status__in=['active', 'trial']
                )
                return client
            except Client.DoesNotExist:
                return None

        return None

    # ========================================== #
    # HELPER: Check Module Access                #
    # ========================================== #
    def check_module_access(self, request):
        """Check karo user ko us module ka access hai ya nahi"""
        if not request.tenant:
            return None

        for module, url_prefix in self.module_urls.items():
            if request.path.startswith(url_prefix):
                if not request.modules.get(module, False):
                    messages.error(
                        request,
                        f'⚠️ {module.replace("_", " ").title()} module is not included in your plan!'
                    )
                    return redirect('dashboard')

        return None


# ========================================== #
# SHAREHOLDER RESTRICTION MIDDLEWARE         #
# ========================================== #
class ShareholderRestrictionMiddleware:
    """Restrict shareholder users to shareholder portal only"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            is_shareholder = hasattr(request.user, 'shareholder_profile')

            if is_shareholder:
                path = request.path

                # Allow static/media
                if path.startswith('/media/') or path.startswith('/static/'):
                    return self.get_response(request)

                # Allow shareholder portal
                if not path.startswith('/shareholder/'):
                    messages.error(request, '⚠️ Access denied!')
                    return redirect('shareholder_portal_dashboard')

        return self.get_response(request)


# ========================================== #
# LIVE VISITOR MIDDLEWARE                    #
# ========================================== #
class LiveVisitorMiddleware:
    """Track live visitors on shop"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/shop/'):
            try:
                from .models import LiveVisitor
                LiveVisitor.track_visitor(request)
            except Exception as e:
                logger.error(f"Live visitor error: {e}")

        return self.get_response(request)


# ========================================== #
# ADMIN ACTIVITY MIDDLEWARE                  #
# ========================================== #
class AdminActivityMiddleware:
    """Track admin presence/activity"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff:
            try:
                path = request.path
                if not path.startswith('/static/') and not path.startswith('/media/'):
                    from .models import AdminPresence
                    AdminPresence.mark_activity(user=request.user, page=path)
            except Exception as e:
                logger.error(f"Admin presence error: {e}")

        return response