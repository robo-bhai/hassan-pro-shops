"""
Run once from the project root (the folder that contains `app/`):

    python apply_step2.py

* registers the new models module   (app/models/__init__.py -> "gl_posting")
* turns on live posting             (app/apps.py -> import app.signals_gl)
Both edits are safe to repeat. Originals are saved as *.bak_gl
"""
import re
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
models_init = root / 'app' / 'models' / '__init__.py'
apps_py = root / 'app' / 'apps.py'


def read(p):
    raw = p.read_bytes().decode('utf-8')
    return raw, ('\r\n' if '\r\n' in raw else '\n')


def write(p, text, nl):
    shutil.copy(p, str(p) + '.bak_gl')
    p.write_bytes(text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8'))


if not models_init.exists() or not apps_py.exists():
    sys.exit('Run this from the project root (the folder that contains app/).')

# 1) models/__init__.py
raw, nl = read(models_init)
if '"gl_posting"' in raw or "'gl_posting'" in raw:
    print('models/__init__.py: already registered')
else:
    m = re.search(r'(_MODULES\s*=\s*\[.*?)(\n\])', raw.replace('\r\n', '\n'), re.S)
    if not m:
        sys.exit('Could not find _MODULES in app/models/__init__.py - add "gl_posting" by hand.')
    text = raw.replace('\r\n', '\n')
    text = text[:m.end(1)] + '\n    "gl_posting",' + text[m.end(1):]
    write(models_init, text, nl)
    print('models/__init__.py: registered gl_posting')

# 2) apps.py
raw, nl = read(apps_py)
if 'signals_gl' in raw:
    print('apps.py: live posting already on')
else:
    text = raw.replace('\r\n', '\n')
    m = re.search(r'^(\s*)import app\.signals(?:_security)?\s*$', text, re.M)
    last = None
    for last in re.finditer(r'^(\s*)import app\.signals\w*\s*$', text, re.M):
        pass
    if not last:
        sys.exit('Could not find the signals import in app/apps.py - add "import app.signals_gl" inside ready() by hand.')
    text = text[:last.end()] + '\n' + last.group(1) + 'import app.signals_gl' + text[last.end():]
    write(apps_py, text, nl)
    print('apps.py: live posting on')

print('\nNext:  python manage.py makemigrations app && python manage.py migrate')
print('       python manage.py post_ledger --setup')
print('       python manage.py post_ledger --backfill     (once, for old documents)')
print('       python manage.py post_ledger --check')
