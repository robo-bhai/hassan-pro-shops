import datetime, json, os
from django.conf import settings
from django.db import connection

TABLES = ["app_client", "app_subscriptionplan", "app_subscriptionhistory", "app_subscriptionpayment"]
LINKS = ["app_customer", "app_employee", "app_product", "app_shareholder", "app_vendor", "app_subscriptionpayment"]

def jsonable(v):
    return v if isinstance(v, (int, float, str, bool, type(None))) else str(v)

data = {"tables": {}, "client_links": {}}
with connection.cursor() as c:
    existing = set(connection.introspection.table_names(c))
    for t in TABLES:
        if t in existing:
            c.execute('SELECT * FROM "%s"' % t)
            cols = [d[0] for d in c.description]
            data["tables"][t] = [dict(zip(cols, map(jsonable, r))) for r in c.fetchall()]
    for t in LINKS:
        if t in existing:
            c.execute('PRAGMA table_info("%s")' % t)
            if any(r[1] == "client_id" for r in c.fetchall()):
                c.execute('SELECT id, client_id FROM "%s" WHERE client_id IS NOT NULL' % t)
                data["client_links"][t] = [[r[0], r[1]] for r in c.fetchall()]
folder = getattr(settings, "BACKUP_DIR", None) or os.path.join(str(settings.BASE_DIR), "dbbackup")
os.makedirs(folder, exist_ok=True)
path = os.path.join(folder, "legacy_saas_export_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print("Saved:", path)
for t, rows in data["tables"].items():
    print("  %-26s %d row(s)" % (t, len(rows)))
for t, rows in data["client_links"].items():
    print("  %-26s %d row(s) linked to a client" % (t + ".client_id", len(rows)))
