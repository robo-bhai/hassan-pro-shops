import os
from pathlib import Path
import socket
import pymysql

# PyMySQL ko MySQLdb ki tarah install karo
pymysql.install_as_MySQLdb()

# ============================================
# EMAIL SETTINGS
# ============================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

# Low Stock Alert Emails
ALERT_FROM_EMAIL = os.environ.get('ALERT_FROM_EMAIL', EMAIL_HOST_USER)
ALERT_TO_EMAIL = os.environ.get('ALERT_TO_EMAIL', EMAIL_HOST_USER)

# ============================================
# ENCRYPTION (GitHub Secret: DJANGO_SALT_KEY)
# ============================================
SALT_KEY = os.environ.get('DJANGO_SALT_KEY')

# ============================================
# BASE DIR
# ============================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# SECURITY SETTINGS (GitHub Secret: DJANGO_SECRET_KEY)
# ============================================
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# DEBUG - Environment variable se control karo
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')

# ALLOWED_HOSTS
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,hadi88.online,shops.hadi88.online').split(',')


# Automatically local network IP detect karke ALLOWED_HOSTS mein add karna
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()
    
    if local_ip not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(local_ip)
except Exception:
    pass

if '0.0.0.0' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('0.0.0.0')

# Cloudflare Tunnel support (.trycloudflare.com subdomains)
ALLOWED_HOSTS.append('.trycloudflare.com')

# ============================================
# CSRF TRUSTED ORIGINS (Cloudflare Fix)
# ============================================
CSRF_TRUSTED_ORIGINS = [
    'https://*.trycloudflare.com',
]

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# ============================================
# SESSION SETTINGS (FIXED)
# ============================================
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False

# ============================================
# INSTALLED APPS
# ============================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'app',
    'dbbackup',
    'import_export',
    'axes',
    'ceo_module',
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
    'app.middleware.ShareholderRestrictionMiddleware',
    'app.middleware.SecurityMiddleware',
]

# ============================================
# AUTHENTICATION
# ============================================
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1

# ============================================
# URLS & TEMPLATES
# ============================================
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

# ============================================
# DATABASE - RESPONSIVE TO GITHUB SECRETS (Aiven MySQL & SQLite Fallback)
# ============================================
# ============================================
# DATABASE - HARDCODED AIVEN CONFIG (PASSWORD FROM SECRET)
# ============================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'defaultdb'),
        'USER': os.environ.get('DB_USER', 'avnadmin'),
        'PASSWORD': os.environ.get('DB_PASS', ''),
        'HOST': os.environ.get('DB_HOST', 'django-hassan-innoxentnomsee-aece.l.aivencloud.com'),
        'PORT': os.environ.get('DB_PORT', '10568'),
        'OPTIONS': {
            'ssl': {
                'ssl-mode': 'REQUIRED',
            },
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}



# ============================================
# FAST DATABASE BACKUP SETTINGS
# ============================================
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

# ============================================
# CACHE SETTINGS
# ============================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

# ============================================
# PASSWORD VALIDATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ============================================
# STATIC FILES
# ============================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ============================================
# DEFAULT AUTO FIELD
# ============================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ============================================
# LOGGING
# ============================================
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

# ============================================
# EXPORT
# ============================================
__all__ = [
    'BACKUP_DIR',
    'BACKUP_PROGRESS_FILE',
    'RCLONE_ENABLED',
    'RCLONE_REMOTE_NAME',
    'RCLONE_REMOTE_DIR',
]
