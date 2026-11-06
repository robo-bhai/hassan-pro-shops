"""Ek baar chalayein (project root se): har models.FileField par storage=raw_media_storage lagata hai.
ImageField default Cloudinary storage par jati hai. Uske baad:  python manage.py makemigrations
(sirf state-only AlterField bante hain, DB data nahi badalta), phir migrations commit karein."""
import pathlib, re
root = pathlib.Path("app/models")
IMPORT = "from app.storage import raw_media_storage\n"
n = 0
for p in root.rglob("*.py"):
    s = p.read_text(encoding="utf-8")
    if "models.FileField(" not in s:
        continue
    new = re.sub(r"models\.FileField\((?![^)]*storage=)", "models.FileField(storage=raw_media_storage, ", s)
    if new == s:
        continue
    if IMPORT not in new:
        m = re.search(r"^(from|import) .*$", new, re.M)
        new = new[:m.start()] + IMPORT + new[m.start():]
    p.write_text(new, encoding="utf-8"); n += 1; print("patched", p)
print("files patched:", n)
