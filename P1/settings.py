import os
from pathlib import Path
import socket
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# --- DATABASE DRIVER SETUP ---
import pymysql
pymysql.install_as_MySQLdb()

# --- KEYS & GENERAL CONFIGURATION ---
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
SALT_KEY = os.environ.get('DJANGO_SALT_KEY')
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')

# --- ALLOWED HOSTS ---
env_allowed = os.environ.get('ALLOWED_HOSTS', '')
if env_allowed:
    ALLOWED_HOSTS = [h.strip() for h in env_allowed.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = []

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

# --- CSRF TRUSTED ORIGINS ---
CSRF_TRUSTED_ORIGINS = []
env_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if env_csrf:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in env_csrf.split(',') if origin.strip()]

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


import os


EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 't')


EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'info@uqn88.store')



# --- SESSION CONFIGURATION ---
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False

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

# --- CLOUDINARY CONFIGURATION (FROM ENVIRONMENT/GIT SECRETS) ---
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.environ.get('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.environ.get('CLOUDINARY_API_KEY'),
    'API_SECRET': os.environ.get('CLOUDINARY_API_SECRET'),
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
    'app.middleware.ShareholderRestrictionMiddleware',
    'app.middleware.LiveVisitorMiddleware',
    'app.middleware.SecurityMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1

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

# --- MYSQL DATABASE CONFIGURATION ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASS'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'ssl': {
                'ssl-mode': 'REQUIRED',
            },
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
        'CONN_MAX_AGE': 60,
    }
}

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

import os

# ============================================
# STATIC FILES & MEDIA
# ============================================

import os
from pathlib import Path

# Static Files Setup
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media Files Setup
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Directory Auto-Creation (Safe Side)
os.makedirs(STATIC_ROOT, exist_ok=True)
os.makedirs(MEDIA_ROOT, exist_ok=True)

# ============================================
# ✅ DYNAMIC STORAGE SETTINGS (Termux / CI / Prod)
# ============================================

# Environment variable check karein (Default: False)
IS_TERMUX = os.getenv('RUNNING_IN_TERMUX', 'false').lower() == 'true'

if IS_TERMUX:
    # Android / Termux ke liye custom storage
    DEFAULT_FILE_STORAGE_BACKEND = "app.custom_storage.TermuxFileSystemStorage"
else:
    # Standard Server / Cloud Storage ke liye Cloudinary
    DEFAULT_FILE_STORAGE_BACKEND = "cloudinary_storage.storage.MediaCloudinaryStorage"

STORAGES = {
    "default": {
        "BACKEND": DEFAULT_FILE_STORAGE_BACKEND,
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'backup_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/backup.log',
            'formatter': 'simple',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/debug.log',
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

LOGS_DIR = BASE_DIR / 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

RCLONE_ENABLED = True
RCLONE_REMOTE_NAME = 'gdrive'
RCLONE_REMOTE_DIR = 'TermuxBackups'

__all__ = [
    'BACKUP_DIR',
    'BACKUP_PROGRESS_FILE',
    'RCLONE_ENABLED',
    'RCLONE_REMOTE_NAME',
    'RCLONE_REMOTE_DIR',
]

PWA_APP_NAME = 'Business Management System'
PWA_APP_SHORT_NAME = 'BMS App'
PWA_APP_DESCRIPTION = "Executive & Business Management Platform"
PWA_APP_THEME_COLOR = '#0d6efd'
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'any'
PWA_APP_START_URL = '/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {
        'src': '/static/ceo/images/icon-192.png',
        'sizes': '192x192',
        'type': 'image/png'
    },
    {
        'src': '/static/ceo/images/icon-512.png',
        'sizes': '512x512',
        'type': 'image/png'
    }
]
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'en-US'
PWA_SERVICE_WORKER_PATH = os.path.join(BASE_DIR, 'static', 'serviceworker.js')
