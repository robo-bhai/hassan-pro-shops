import os
import io
import json
import base64
import glob
import sys
from datetime import datetime
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

# Tables to skip during restore to protect live authentication states
EXCLUDE_TABLES = {
    'auth_user', 
    'auth_group', 
    'auth_permission', 
    'auth_user_groups', 
    'auth_user_user_permissions',
    'users'
}

# --- 2. ENGINE BUILDER ---
def get_db_engine():
    db_uri = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    engine_options = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    if db_host and db_host != '127.0.0.1':
        engine_options['connect_args'] = {'ssl': {'ssl_mode': 'REQUIRED'}}
    
    return create_engine(db_uri, **engine_options)

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
            
            for row in rows:
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()

            backup_data[table] = rows

    json_payload = json.dumps(
        backup_data,
        default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o),
    )
    encrypted_content = encrypt_data(json_payload)

    if output_filename:
        with open(output_filename, "wb") as f:
            f.write(encrypted_content)
        print(f"✅ Backup successfully encrypted and saved to: {output_filename}\n")

    return encrypted_content

# --- 5. HELPER FOR LATEST FILE ---
def get_latest_enc_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    enc_files = glob.glob(os.path.join(script_dir, "*.enc"))
    if not enc_files:
        return None
    return max(enc_files, key=os.path.getmtime)

# --- 6. CORE RESTORE FROM BYTES ---
def execute_restore_from_bytes(file_bytes: bytes):
    try:
        decrypted_str = decrypt_data(file_bytes)
        backup_data = json.loads(decrypted_str)
    except Exception as e:
        msg = f"Decryption Failed! Invalid Secret Key or Corrupted File. Details: {e}"
        print(f"💥 {msg}")
        return False, msg

    engine = get_db_engine()
    inspector = inspect(engine)

    schema_is_valid = True
    missing_tables = []
    missing_columns = {}

    # Pre-Restore Schema Comparison (Ignoring EXCLUDE_TABLES)
    for table_name, rows in backup_data.items():
        if table_name in EXCLUDE_TABLES:
            continue

        if not inspector.has_table(table_name):
            schema_is_valid = False
            missing_tables.append(table_name)
            continue

        if not rows:
            continue

        target_db_cols = {col['name'] for col in inspector.get_columns(table_name)}
        backup_cols = set(rows[0].keys())
        unmatched_cols = backup_cols - target_db_cols

        if unmatched_cols:
            schema_is_valid = False
            missing_columns[table_name] = list(unmatched_cols)

    if not schema_is_valid:
        msg = f"Schema Mismatch! Missing tables: {missing_tables}, Missing columns: {missing_columns}"
        print(f"⛔ RESTORE CANCELLED! {msg}")
        return False, msg

    try:
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

            for table_name, rows in backup_data.items():
                if table_name in EXCLUDE_TABLES:
                    print(f"⏩ Skipping table `{table_name}` (Preserving credentials).")
                    continue

                if not rows:
                    continue

                conn.execute(text(f"TRUNCATE TABLE `{table_name}`;"))

                for row in rows:
                    for k, v in row.items():
                        if isinstance(v, str) and 'T' in v and len(v) >= 19:
                            try:
                                row[k] = v.replace('T', ' ').split('.')[0]
                            except Exception:
                                pass

                columns = list(rows[0].keys())
                col_names_str = ", ".join([f"`{col}`" for col in columns])
                val_placeholders = ", ".join([f":{col}" for col in columns])
                
                insert_sql = text(f"INSERT INTO `{table_name}` ({col_names_str}) VALUES ({val_placeholders})")
                conn.execute(insert_sql, rows)
                print(f"⚡ Table `{table_name}`: Restored {len(rows)} records successfully.")

            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        msg = "Full Restore Completed Successfully!"
        print(f"🎉 {msg}")
        return True, msg

    except Exception as e:
        msg = f"Restore Failed! Details: {e}"
        print(f"💥 {msg}")
        return False, msg

# --- 7. CLI / FILE RESTORE ---
def restore_backup(backup_filepath=None):
    if not backup_filepath:
        backup_filepath = get_latest_enc_file()

    if not backup_filepath or not os.path.exists(backup_filepath):
        print("❌ Error: No valid `.enc` backup file found.")
        return False, "File not found"

    print(f"🔓 Processing restore file: {backup_filepath}...")
    with open(backup_filepath, "rb") as f:
        file_bytes = f.read()

    return execute_restore_from_bytes(file_bytes)

# --- 8. CLI INTERFACE ---
if __name__ == "__main__":
    print("--------------------------------------------------")
    print("      MySQL Secure Backup & Safe Restore          ")
    print("--------------------------------------------------")
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Take Backup:    python db_backup_manager.py backup")
        print("  Restore Backup: python db_backup_manager.py restore [backup_file_path]")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "backup":
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{db_name}_{timestamp}.enc"
        export_backup(filename)
    elif action == "restore":
        filepath = sys.argv[2] if len(sys.argv) >= 3 else None
        success, msg = restore_backup(filepath)
        if not success:
            sys.exit(1)
    else:
        print("❌ Invalid command! Use 'backup' or 'restore'.")
        sys.exit(1)
