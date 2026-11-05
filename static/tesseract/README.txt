Is folder mein Tesseract (OCR) ki files aani chahiyen. Ek baar internet wale computer par project root se chalayen:

    python scripts/utilities/fetch_tesseract_assets.py

Phir server par (agar use karte hain):  python manage.py collectstatic

Expected layout:
    tesseract.min.js
    worker.min.js
    core/tesseract-core*.wasm.js   (4 files)
    lang/eng.traineddata
    lang/urd.traineddata

Jab tak ye files nahi hotin, OCR CDN se chalta hai (internet chahiye). Files aane ke baad OCR local se load hota hai
aur service worker unhein browser mein cache kar leta hai.
