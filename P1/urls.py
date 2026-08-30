from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

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

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    if hasattr(settings, 'MEDIA_URL') and hasattr(settings, 'MEDIA_ROOT'):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
