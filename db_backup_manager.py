import os
import io
import json
import base64
from datetime import datetime, date
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

load_dotenv()

# --- 1. CONFIGURATION ---
db_user = os.environ.get('DB_USER')
db_pass = os.environ.get('DB_PASS')
db_host = os.environ.get('DB_HOST')
db_port = int(os.environ.get('DB_PORT', '3306'))
db_name = os.environ.get('DB_NAME')

if not all([db_user, db_pass, db_host, db_name]):
    raise ValueError("CRITICAL ERROR: Database environment variables (DB_USER, DB_PASS, DB_HOST, DB_NAME) missing!")

ENCRYPTION_SECRET = os.environ.get('BACKUP_SECRET_KEY')
if not ENCRYPTION_SECRET:
    raise ValueError("CRITICAL ERROR: BACKUP_SECRET_KEY environment variable missing!")

# --- 2. ENGINE BUILDER ---
def get_db_engine():
    db_uri = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    engine_options = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    if db_host != '127.0.0.1':
        engine_options['connect_args'] = {'ssl': {'ssl_mode': 'REQUIRED'}}
    
    return create_engine(db_uri, **engine_options)

# Custom JSON Serializer for Date, Datetime, Decimal & non-standard types
def json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

# --- 3. ENCRYPTION HELPERS ---
def _derive_key(salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(ENCRYPTION_SECRET.encode()))

def encrypt_data(data_str: str) -> bytes:
    salt = os.urandom(16)
    key = _derive_key(salt)
    fernet = Fernet(key)
    encrypted_bytes = fernet.encrypt(data_str.encode('utf-8'))
    return salt + encrypted_bytes

def decrypt_data(file_bytes: bytes) -> str:
    salt = file_bytes[:16]
    encrypted_bytes = file_bytes[16:]
    key = _derive_key(salt)
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_bytes).decode('utf-8')

# --- 4. BACKUP FUNCTION ---
def export_backup(output_filename=None):
    if not output_filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"backup_{db_name}_{timestamp}.enc"

    engine = get_db_engine()
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    backup_data = {}

    print(f"📦 Starting Encrypted Backup for Database: [{db_name}]...")

    with engine.connect() as conn:
        for table in tables:
            print(f"  ➜ Exporting table: {table}")
            result = conn.execute(text(f"SELECT * FROM `{table}`"))
            rows = [dict(row._mapping) for row in result]
            backup_data[table] = rows

    # Custom serializer pass kiya hai taake date, datetime & decimal crash na hon
    json_payload = json.dumps(backup_data, default=json_serializer)
    encrypted_content = encrypt_data(json_payload)

    with open(output_filename, "wb") as f:
        f.write(encrypted_content)

    print(f"✅ Backup successfully encrypted and saved to: {output_filename}\n")

# --- 5. STRICT ATOMIC RESTORE FUNCTION ---
def restore_backup(backup_filepath):
    if not os.path.exists(backup_filepath):
        print(f"❌ Error: Backup file '{backup_filepath}' not found.")
        return

    print(f"🔓 Decrypting backup file: {backup_filepath}...")
    try:
        with open(backup_filepath, "rb") as f:
            file_bytes = f.read()
        decrypted_str = decrypt_data(file_bytes)
        backup_data = json.loads(decrypted_str)
    except Exception as e:
        print(f"💥 Decryption Failed! Invalid Key or Corrupted File. Details: {e}")
        return

    engine = get_db_engine()
    inspector = inspect(engine)

    print("\n" + "="*60)
    print("🔍 PRE-RESTORE SCHEMA VALIDATION CHECK")
    print("="*60)

    schema_is_valid = True
    missing_tables = []
    missing_columns = {}
    existing_columns_report = {}

    for table_name, rows in backup_data.items():
        if not inspector.has_table(table_name):
            schema_is_valid = False
            missing_tables.append(table_name)
            continue

        if not rows:
            continue

        target_db_cols = {col['name'] for col in inspector.get_columns(table_name)}
        backup_cols = set(rows[0].keys())

        matched_cols = backup_cols.intersection(target_db_cols)
        unmatched_cols = backup_cols - target_db_cols

        existing_columns_report[table_name] = list(matched_cols)

        if unmatched_cols:
            schema_is_valid = False
            missing_columns[table_name] = list(unmatched_cols)

    print("\n📊 --- SCHEMA COMPARISON REPORT ---")

    for tbl, cols in existing_columns_report.items():
        print(f"✅ Table `{tbl}`: {len(cols)} column(s) matched in target DB.")

    if missing_tables:
        print("\n❌ MISSING TABLES IN TARGET DB:")
        for tbl in missing_tables:
            print(f"   - `{tbl}` (Whole table missing)")

    if missing_columns:
        print("\n⚠️  MISSING COLUMNS IN TARGET DB:")
        for tbl, cols in missing_columns.items():
            print(f"   - Table `{tbl}` missing column(s): {', '.join(cols)}")

    if not schema_is_valid:
        print("\n" + "🚨"*30)
        print("⛔ RESTORE CANCELLED! Database Schema Mismatch Detected.")
        print("   Ek bhi record restore nahi kiya gaya hai.")
        print("🚨"*30)
        return

    print("\n✅ All tables and columns perfectly match! Proceeding with full restore...")

    with engine.begin() as conn:
        for table_name, rows in backup_data.items():
            if not rows:
                continue

            columns = list(rows[0].keys())
            col_names_str = ", ".join([f"`{col}`" for col in columns])
            val_placeholders = ", ".join([f":{col}" for col in columns])
            insert_sql = text(f"INSERT INTO `{table_name}` ({col_names_str}) VALUES ({val_placeholders})")

            conn.execute(insert_sql, rows)
            print(f"⚡ Table `{table_name}`: Restored {len(rows)} records successfully.")

    print("\n🎉 FULL RESTORE COMPLETED SUCCESSFULLY!")

# --- 6. CLI INTERFACE ---
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Take Backup:    python db_backup_manager.py backup")
        print("  Restore Backup: python db_backup_manager.py restore <backup_file_path>")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "backup":
        export_backup()
    elif action == "restore":
        if len(sys.argv) < 3:
            print("❌ Error: Please provide the path to the backup file.")
        else:
            restore_backup(sys.argv[2])
    else:
        print("❌ Invalid command! Use 'backup' or 'restore'.")
