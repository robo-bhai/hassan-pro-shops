import glob, gzip, os, shutil, sqlite3, tempfile, datetime
paths = set()
for pat in ["db.sqlite3*", "dbbackup/*", "*.sqlite3*", "../*.sqlite3*", "../dbbackup/*", "../*/dbbackup/*"]:
    paths |= set(glob.glob(pat))
TABLES = ["app_client", "auth_user", "app_product", "app_customer", "app_sale", "app_employee", "app_shareholder"]
print("%-52s %7s %-16s %s" % ("file", "MB", "date", " ".join(t.replace("app_", "")[:8] for t in TABLES)))
rows = []
for p in sorted(paths, key=lambda x: os.path.getmtime(x), reverse=True):
    if not os.path.isfile(p):
        continue
    tmp = None
    try:
        path = p
        if p.endswith(".gz"):
            tmp = tempfile.mktemp(suffix=".sqlite3")
            with gzip.open(p, "rb") as a, open(tmp, "wb") as b:
                shutil.copyfileobj(a, b)
            path = tmp
        with open(path, "rb") as f:
            if f.read(15) != b"SQLite format 3":
                continue
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        have = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        counts = []
        for t in TABLES:
            counts.append(str(con.execute('select count(*) from "%s"' % t).fetchone()[0]) if t in have else "-")
        con.close()
        d = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
        print("%-52s %7.1f %-16s %s" % (p[-52:], os.path.getsize(p) / 1e6, d, "  ".join("%8s" % c for c in counts)))
    except Exception as e:
        print("%-52s  (nahi khula: %s)" % (p[-52:], str(e)[:40]))
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
