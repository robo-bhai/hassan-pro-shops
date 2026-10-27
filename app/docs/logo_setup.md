# Logo lagane ke steps

## Ready files (replace them in your project)
| File | Kya badla |
|---|---|
| `sidebar.html` | Emoji ki jagah logo (logo na ho to emoji) |
| `context_processors.py` | `_company_branding()` was added to your current file and added to the return value of `system_settings`. The rest of the code was not touched. |
| `company.html` | `enctype` in the form, the logo field, a preview of the current logo, and a "Remove logo" checkbox |
| `dashboard.py` | Logo upload in the `company_settings` view (2MB limit, only PNG/JPG/WEBP, checked with Pillow) |

No new registration is needed in `context_processors.py`, because `system_settings` is already registered.

## 2 things you need to check yourself
1. Make sure both of these are present in `settings.py`:
```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```
2. At the end of the project `urls.py` (for development):
```python
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```
In production, serve `/media/` from nginx (or your web server).

Pillow must be installed (`pip install pillow`). It is already required for `ImageField`.

## Test
Open Company Settings, upload a logo, save, then open any page. The logo should appear in the sidebar.
