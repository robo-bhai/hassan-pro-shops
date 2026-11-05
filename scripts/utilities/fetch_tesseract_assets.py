"""Download the Tesseract.js files once, so the OCR works without internet / CDN.

Run on a computer WITH internet, from the project root:
    python scripts/utilities/fetch_tesseract_assets.py
    python scripts/utilities/fetch_tesseract_assets.py --dest static/tesseract     (default)

Result (the page expects exactly this layout, URL = {% static 'tesseract/' %}):
    static/tesseract/tesseract.min.js
    static/tesseract/worker.min.js
    static/tesseract/core/tesseract-core*.wasm.js      (4 files: plain / simd / lstm / simd-lstm)
    static/tesseract/lang/eng.traineddata
    static/tesseract/lang/urd.traineddata

Then run `python manage.py collectstatic` on the server if you use it. If your project keeps static files in
another folder (STATICFILES_DIRS), pass that folder with --dest.
"""
import argparse
import os
import sys
import urllib.request

JS_VER = '5.1.1'
CORE_VERS = ['5.1.1', '5.1.0', '5.0.2']           # tried in this order
CORE_FILES = ['tesseract-core.wasm.js', 'tesseract-core-simd.wasm.js',
              'tesseract-core-lstm.wasm.js', 'tesseract-core-simd-lstm.wasm.js']
LANGS = ['eng', 'urd']
LANG_URL = 'https://github.com/tesseract-ocr/tessdata_fast/raw/main/%s.traineddata'


def get(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as f:
        data = r.read()
        f.write(data)
    print('  ok  %-40s %7.1f KB' % (os.path.relpath(dest), len(data) / 1024))


def main():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap = argparse.ArgumentParser()
    ap.add_argument('--dest', default=os.path.join(root, 'static', 'tesseract'))
    dest = ap.parse_args().dest
    failed = []

    for name in ('tesseract.min.js', 'worker.min.js'):
        try:
            get('https://cdn.jsdelivr.net/npm/tesseract.js@%s/dist/%s' % (JS_VER, name), os.path.join(dest, name))
        except Exception as e:
            failed.append((name, e))

    for name in CORE_FILES:
        for v in CORE_VERS:
            try:
                get('https://cdn.jsdelivr.net/npm/tesseract.js-core@%s/%s' % (v, name), os.path.join(dest, 'core', name))
                break
            except Exception as e:
                last = e
        else:
            failed.append((name, last))

    for lang in LANGS:
        try:
            get(LANG_URL % lang, os.path.join(dest, 'lang', lang + '.traineddata'))
        except Exception as e:
            failed.append((lang + '.traineddata', e))

    if failed:
        print('\nFAILED:')
        for n, e in failed:
            print('  %s -> %s' % (n, e))
        print('\nThe page still works: missing local files fall back to the CDN (needs internet).')
        return 1
    print('\nAll files downloaded to', dest)
    return 0


if __name__ == '__main__':
    sys.exit(main())
