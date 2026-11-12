# Forgot password - setup (settings.py mein lagana baaqi hai)

settings.py zip mein nahi tha, is liye yeh hissa aap ko khud lagana hai.

## 1. Redis cache (rate limit sab workers mein sahi chalne ke liye)
`pip install redis` (requirements: `redis>=5.0`), `.env` mein `REDIS_URL=redis://127.0.0.1:6379/1`

```python
REDIS_URL = os.environ.get('REDIS_URL', '').strip()
if REDIS_URL:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                          'LOCATION': REDIS_URL, 'TIMEOUT': 300, 'KEY_PREFIX': 'erp'}}
# warna jo cache pehle se hai wohi chalti rahegi
```

## 2. WhatsApp (optional)
```python
WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '').strip()
WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN', '').strip()
WHATSAPP_OTP_TEMPLATE = os.environ.get('WHATSAPP_OTP_TEMPLATE', '').strip()   # Authentication template
WHATSAPP_TEMPLATE_LANG = os.environ.get('WHATSAPP_TEMPLATE_LANG', 'en').strip()
WHATSAPP_API_VERSION = os.environ.get('WHATSAPP_API_VERSION', 'v21.0').strip()
WHATSAPP_NOTICE_TEMPLATE = os.environ.get('WHATSAPP_NOTICE_TEMPLATE', '').strip()  # optional Utility template
```
Set na hon to kuch nahi bheja jata; rider ka code manager ko Riders page par dikhta hai.

## 3. Proxy ke peeche (nginx/Cloudflare)
IP limits `utils.security.get_client_ip` use karte hain. Reverse proxy ke peeche
`SECURITY_TRUSTED_PROXY_COUNT = 1` (apne proxies ki ginti) set karein, warna sab users ek hi IP lagenge.

## 4. Migration
`python manage.py migrate` (0050: sirf choices badalti hain).

## 5. Tests
`python manage.py test app.tests_password_reset -v 2`
