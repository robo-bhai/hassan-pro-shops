from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.shortcuts import redirect
from django.views.static import serve

# Custom Handlers
handler404 = 'app.views.custom_page_not_found'
handler500 = 'app.views.custom_server_error'

urlpatterns = [
    # Admin Panel
    path('admin/', admin.site.urls),
    
    # Frontend (All app URLs)
    path('', include('app.urls')),
    
    # CEO Module
    path('ceo/', include('ceo_module.urls')),
    
    # Progressive Web App (PWA) URLs
    path('', include('pwa.urls')),
    
    # Redirect /accounts/login/ to /login/
    path('accounts/login/', lambda request: redirect('/login/')),
    
    # GET logout redirect (Django 5.x fix)
    path('accounts/logout/', lambda request: redirect('/logout-redirect/')),
    path('logout-redirect/', lambda request: redirect('/login/'), name='logout_redirect'),
]

# Force-serve media and static files in CI/CD Runner & Cloudflare Tunnel
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
]
