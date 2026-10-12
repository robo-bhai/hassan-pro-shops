# Logo lagane ke steps

## Tayyar files (apne project mein replace karein)
| File | Kya badla |
|---|---|
| `sidebar.html` | Emoji ki jagah logo (logo na ho to emoji) |
| `context_processors.py` | Aap ki maujooda file mein `_company_branding()` add hui aur `system_settings` ke return mein jor di gayi. Baqi code nahi chhua. |
| `company.html` | Form mein `enctype`, logo ka field, mojooda logo ka preview, "Logo hata dein" checkbox |
| `dashboard.py` | `company_settings` view mein logo upload (2MB limit, sirf PNG/JPG/WEBP, Pillow se check) |

`context_processors.py` mein koi nayi registration nahi chahiye, kyunke `system_settings` pehle se registered hai.

## Aap ko khud check karne wale 2 kaam
1. `settings.py` mein yeh dono maujood hon:
```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```
2. Project ki `urls.py` ke aakhir mein (development ke liye):
```python
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```
Production mein `/media/` nginx (ya web server) se serve karwayein.

Pillow install hona chahiye (`pip install pillow`). `ImageField` ke liye woh pehle se zaroori hai.

## Test
Company Settings kholen, logo upload karen, save karen, phir koi bhi page kholen. Sidebar mein logo aana chahiye.
