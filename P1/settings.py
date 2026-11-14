import os
from pathlib import Path
import socket
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# ✅ .env FILE LOAD
# ============================================
from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from django.core.exceptions import ImproperlyConfigured


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('true', '1', 'yes', 't')


# Production-safe defaults: with no .env a fresh install is DEBUG=False and refuses to start without
# real secrets. For development put DEBUG=True (and RUNNING_IN_TERMUX=true on Termux) in your .env.
DEBUG = _env_bool('DEBUG', False)
IS_TERMUX = _env_bool('RUNNING_IN_TERMUX', False)
HTTPS = _env_bool('HTTPS', False)                 # true when the site is served over https
BEHIND_PROXY = _env_bool('BEHIND_PROXY', False)   # true only behind nginx/caddy/IIS that sets X-Forwarded-*

# --- KEYS & GENERAL CONFIGURATION ---
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
SALT_KEY = os.environ.get('DJANGO_SALT_KEY', '')
if not DEBUG:
    for _name, _value in (('DJANGO_SECRET_KEY', SECRET_KEY), ('DJANGO_SALT_KEY', SALT_KEY)):
        if not _value or 'insecure' in _value or 'fallback' in _value or 'change-me' in _value:
            raise ImproperlyConfigured(f'{_name} is missing or a placeholder. Run deploy/setup_install.py (it writes a .env '
                                       f'with random keys) or set it in the .env file.')
else:
    SECRET_KEY = SECRET_KEY or 'django-insecure-dev-only-key'
    SALT_KEY = SALT_KEY or 'dev-only-salt-key'

# Software license (see app/licensing). The PUBLIC key is not a secret, but keep it here in the code,
# not in .env, so that deleting a .env line cannot switch licensing off. Empty = licensing off (development).
# Paste the key printed by:  python make_license.py keygen
LICENSE_PUBLIC_KEY = '642aed2cdc7df044a4658c69d67c2c09067f60d82c0a65dfdd852bded199fed5'

# --- ALLOWED HOSTS ---
env_allowed = os.environ.get('ALLOWED_HOSTS', '')
if env_allowed:
    ALLOWED_HOSTS = [h.strip() for h in env_allowed.split(',') if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = []
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
    try:
        ALLOWED_HOSTS.append(socket.gethostname())
    except Exception:
        pass

# Automatic Local IP Resolution
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()
    
    if local_ip and local_ip not in ALLOWED_HOSTS and '*' not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(local_ip)
except Exception:
    pass

# This computer itself must always work, even when ALLOWED_HOSTS in .env lists only other addresses.
if '*' not in ALLOWED_HOSTS:
    for _loopback in ('localhost', '127.0.0.1', '[::1]'):
        if _loopback not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_loopback)

# --- CSRF TRUSTED ORIGINS ---
CSRF_TRUSTED_ORIGINS = []
env_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if env_csrf:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in env_csrf.split(',') if origin.strip()]

if BEHIND_PROXY:
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --- EMAIL CONFIGURATION ---
def _env_first(*names):
    """Pehla non-empty environment variable (GitHub Secrets / .env)."""
    for n in names:
        v = os.environ.get(n, '').strip()
        if v:
            return v
    return ''

# Brevo API (GitHub Secrets se): key + sender name + sender email
BREVO_API_KEY = _env_first('BREVO_API_KEY', 'BREVO_KEY', 'SENDINBLUE_API_KEY')
BREVO_SENDER_NAME = _env_first('BREVO_SENDER_NAME', 'SENDER_NAME', 'EMAIL_SENDER_NAME') or 'UQN88 Store'
BREVO_SENDER_EMAIL = _env_first('BREVO_SENDER_EMAIL', 'SENDER_EMAIL', 'EMAIL_SENDER_EMAIL')

# Purana SMTP tareeqa (sirf tab jab Brevo API ki secrets maujood na hon)
# Naye order ki admin email (comma separated). Admin/staff users ki email ke ilawa yahan bhi bhej sakte hain.
# .env mein: ORDER_ALERT_EMAILS=owner@example.com,manager@example.com
ORDER_ALERT_EMAILS = [e.strip() for e in os.environ.get('ORDER_ALERT_EMAILS', '').split(',') if e.strip()]

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')

if BREVO_API_KEY and BREVO_SENDER_EMAIL:
    EMAIL_BACKEND = 'app.utils.brevo_backend.BrevoAPIEmailBackend'
    DEFAULT_FROM_EMAIL = BREVO_SENDER_EMAIL      # sirf email (display name backend lagata hai)
else:
    EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
    DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'info@uqn88.store')

# --- SESSION CONFIGURATION ---
# Session & CSRF Settings
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True

# Updated Cookie Settings for Cross-Site / Frontend-Backend separation (e.g., React/Flutter & Django)
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SECURE = True

# Security Settings
SECURE_SSL_REDIRECT = HTTPS and not DEBUG
SECURE_HSTS_SECONDS = 31536000 if (HTTPS and not DEBUG) else 0
SECURE_CONTENT_TYPE_NOSNIFF = True



FRAME_ANCESTORS = ["https://kwlconnect.online"]   # jahan se Khanewal Connect app khulti hai





INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'pwa',
    'django.contrib.messages',
    'cloudinary_storage',
    'django.contrib.staticfiles',
    'cloudinary',
    'django.contrib.humanize',
    'app',
    'dbbackup',
    'import_export',
    'axes',
    'ceo_module',
]

# --- CLOUDINARY CONFIGURATION ---
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'app.module_access.ModuleAccessMiddleware',   # blocks URLs of OFF modules / roles without access
    'axes.middleware.AxesMiddleware',
    'app.middleware.SecurityMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'app.middleware.frame_embed.AllowAppFraming',
    'app.middleware.license_gate.LicenseMiddleware',
  #  "django.middleware.clickjacking.XFrameOptionsMiddleware",
       # XFrameOptionsMiddleware ke BAAD likhein

    # Custom Middleware
    'app.middleware.ShareholderRestrictionMiddleware',
    'app.security.security_2fa.TwoFactorMiddleware',
    'app.middleware.LiveVisitorMiddleware',
    'app.middleware.AdminActivityMiddleware',
]

try:                                   # serves /static/ when DEBUG is False (pip install whitenoise)
    import whitenoise  # noqa: F401
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 100
AXES_COOLOFF_TIME = 0.001

ROOT_URLCONF = 'P1.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, "templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'app.context_processors.system_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'P1.wsgi.application'

# ==========================================
# ✅ DATABASE - SQLite (LOCAL TERMUX)
# ==========================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 30},        # wait up to 30s for a lock instead of "database is locked"
    }
}

# ==========================================
# ✅ DATABASE - MySQL (GitHub runner local MySQL)
# Used only when DB_HOST is set (deploy.yml sets it). Without DB_HOST the SQLite above stays active,
# so Termux / customer installs keep working unchanged. Needs: pip install mysqlclient
# ==========================================
if os.environ.get('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('DB_NAME', 'local_django_db'),
            'USER': os.environ.get('DB_USER', 'root'),
            'PASSWORD': os.environ.get('DB_PASS', ''),
            'HOST': os.environ['DB_HOST'],
            'PORT': os.environ.get('DB_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }

if not IS_TERMUX:
    # WAL lets readers and one writer work at the same time (several cashiers). Not used on Termux/shared
    # storage where WAL files are not supported. The backup system uses SQLite's own backup API, so it is safe with WAL.
    from django.db.backends.signals import connection_created

    def _sqlite_pragmas(sender, connection, **kwargs):
        if connection.vendor == 'sqlite':
            cursor = connection.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')

    connection_created.connect(_sqlite_pragmas)

# --- DB BACKUP CONFIGURATION ---
DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {
    'location': BASE_DIR / 'dbbackup',
    'compress': True,
}
DBBACKUP_FORMAT = 'gzip'
DBBACKUP_COMPRESS_LEVEL = 1
DBBACKUP_TMP_FILE_MAX_SIZE = 500 * 1024 * 1024
DBBACKUP_CLEANUP_KEEP = 5
DBBACKUP_HOSTNAME = 'geek'

BACKUP_DIR = str(BASE_DIR / 'dbbackup')
os.makedirs(BACKUP_DIR, exist_ok=True)
BACKUP_PROGRESS_FILE = str(BASE_DIR / 'dbbackup' / 'backup_progress.json')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': BASE_DIR / 'django_cache',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ============================================
# STATIC FILES & MEDIA
# ============================================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

os.makedirs(STATIC_ROOT, exist_ok=True)
os.makedirs(MEDIA_ROOT, exist_ok=True)

# ============================================
# ✅ STORAGE (Local FileSystem)
# ============================================
# Media (logo, documents) is stored on this computer unless MEDIA_STORAGE=cloudinary is set in .env
# (cloudinary needs internet and the CLOUDINARY_* keys).
if IS_TERMUX:
    DEFAULT_FILE_STORAGE_BACKEND = "app.custom_storage.TermuxFileSystemStorage"
elif os.environ.get('MEDIA_STORAGE', 'local').strip().lower() == 'cloudinary':
    DEFAULT_FILE_STORAGE_BACKEND = "cloudinary_storage.storage.MediaCloudinaryStorage"
else:
    DEFAULT_FILE_STORAGE_BACKEND = "django.core.files.storage.FileSystemStorage"
if DEBUG:
    print(f"[STORAGE] {DEFAULT_FILE_STORAGE_BACKEND}")

STORAGES = {
    "default": {
        "BACKEND": DEFAULT_FILE_STORAGE_BACKEND,
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Django 5.1 removed these two settings, but django-cloudinary-storage's collectstatic still reads them
# ("AttributeError: 'Settings' object has no attribute 'STATICFILES_STORAGE'"). Keep them in step with STORAGES.
STATICFILES_STORAGE = STORAGES["staticfiles"]["BACKEND"]
DEFAULT_FILE_STORAGE = STORAGES["default"]["BACKEND"]

# ============================================
# ✅ TERMUX FILE LOCKING FIX
# ============================================
if IS_TERMUX:                      # shared storage on Android has no file locks; never disable them on a real server
    try:
        import django.core.files.locks as locks_module
        locks_module.lock = lambda f, flags: True
        locks_module.unlock = lambda f: True
        locks_module.is_locked = lambda f: False
        print("✅ [TERMUX FIX] File locking disabled")
    except Exception as e:
        print(f"⚠️ [TERMUX FIX] Failed: {e}")

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {asctime} {message}', 'style': '{'},
    },
    'handlers': {
        'backup_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/backup.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'simple',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs/debug.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'app.backup': {
            'handlers': ['backup_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ============================================ #
# ✅ DJANGO ADMIN - FILE UPLOAD & FIELD LIMITS #
# ============================================ #
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800

LOGS_DIR = BASE_DIR / 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

RCLONE_ENABLED = True
RCLONE_REMOTE_NAME = 'gdrive'
RCLONE_REMOTE_DIR = 'TermuxBackups'

# ============================================ #
# ✅ PROFESSIONAL BACKUP SYSTEM (app/backup_service.py)
# ============================================ #
# Retention (GFS): 7 daily, 4 weekly, 12 monthly. Pichle 24 ghante ke sab backups rehte hain.
BACKUP_KEEP = {'daily': 7, 'weekly': 4, 'monthly': 12, 'recent_hours': 24}
BACKUP_INCLUDE_MEDIA = True       # media/ folder (logo, documents) bhi backup ho
BACKUP_MAX_AGE_HOURS = 26         # is se purana last backup = "unhealthy"
BACKUP_NOTIFY_EMAIL = []          # backup fail ho to email, e.g. ['owner@example.com']

PWA_APP_NAME = 'Khanewal Connect'
PWA_APP_SHORT_NAME = 'Khanewal Connect'
PWA_APP_DESCRIPTION = "Khanewal Connect - Delivery, Home Services, Relocation"
PWA_APP_THEME_COLOR = '#1e3a8a'
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/shop/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {'src': '/static/icons/icon-192x192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
    {'src': '/static/icons/icon-512x512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
    {'src': '/static/icons/icon-maskable-512x512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
]
PWA_APP_ICONS_APPLE = [
    {'src': '/static/icons/apple-touch-icon.png', 'sizes': '180x180', 'type': 'image/png'},
]
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'en-US'
PWA_SERVICE_WORKER_PATH = os.path.join(BASE_DIR, 'static', 'serviceworker.js')