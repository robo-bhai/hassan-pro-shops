import glob, gzip, json, os, shutil, sqlite3, datetime
cands = set()
for pat in ["dbbackup/*", "../dbbackup/*", "../*/dbbackup/*", "*.sqlite3*"]:
    cands |= set(glob.glob(pat))
TABLES = ["app_client", "app_subscriptionplan", "app_subscriptionhistory", "app_subscriptionpayment"]
LINKS = ["app_customer", "app_employee", "app_product", "app_shareholder", "app_vendor", "app_subscriptionpayment"]
best = None
for p in sorted([c for c in cands if os.path.isfile(c)], key=os.path.getmtime, reverse=True):
    tmp = "_tmp_old.sqlite3"
    try:
        if p.endswith(".gz"):
            with gzip.open(p, "rb") as a, open(tmp, "wb") as b:
                shutil.copyfileobj(a, b)
            path = tmp
        else:
            path = p
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        have = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        if "app_client" in have and con.execute("select count(*) from app_client").fetchone()[0] > 0:
            best = (p, path, con, have)
            break
        con.close()
    except Exception:
        pass
if not best:
    raise SystemExit("Koi backup nahi mili jis mein app_client ke rows hon.")
p, path, con, have = best
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
os.makedirs("dbbackup", exist_ok=True)
keep = "dbbackup/OLD_SAAS_COPY_%s.sqlite3" % stamp
shutil.copyfile(path, keep)
data = {"source": p, "tables": {}, "client_links": {}}
def jv(v):
    return v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
for t in TABLES:
    if t in have:
        cur = con.execute('select * from "%s"' % t)
        cols = [d[0] for d in cur.description]
        data["tables"][t] = [dict(zip(cols, map(jv, r))) for r in cur.fetchall()]
for t in LINKS:
    if t in have and any(r[1] == "client_id" for r in con.execute('pragma table_info("%s")' % t)):
        data["client_links"][t] = [list(r) for r in con.execute('select id, client_id from "%s" where client_id is not null' % t)]
out = "dbbackup/old_saas_export_%s.json" % stamp
json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
con.close()
if os.path.exists("_tmp_old.sqlite3"):
    os.remove("_tmp_old.sqlite3")
print("Source backup :", p)
print("Poori copy    :", keep)
print("JSON export   :", out)
for t, rows in data["tables"].items():
    print("  %-26s %d row(s)" % (t, len(rows)))
for t, rows in data["client_links"].items():
    print("  %-26s %d row(s) kisi client se jura" % (t + ".client_id", len(rows)))
for r in data["tables"].get("app_client", []):
    print("  client:", r.get("id"), r.get("business_name"), r.get("subdomain"), r.get("subscription_status"), r.get("subscription_end"))
