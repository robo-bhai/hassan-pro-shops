import os
import io
import json
import base64
import glob
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
load_dotenv()

# --- 1. CONFIGURATION LOADED FROM CI/CD & ENV ---

# Cloud Database Credentials (From GitHub Secrets / Env Variables)
CLOUD_DB_USER = os.environ.get('DB_USER')
CLOUD_DB_PASS = os.environ.get('DB_PASS')
CLOUD_DB_HOST = os.environ.get('DB_HOST')
CLOUD_DB_PORT = int(os.environ.get('DB_PORT', '3306'))
CLOUD_DB_NAME = os.environ.get('DB_NAME')

# Local Database Credentials (Explicit LOCAL_DB_* or YAML Fallback: root@127.0.0.1:3306/local_django_db)
LOCAL_DB_USER = os.environ.get('LOCAL_DB_USER', 'root')
LOCAL_DB_PASS = os.environ.get('LOCAL_DB_PASS', 'root')
LOCAL_DB_HOST = os.environ.get('LOCAL_DB_HOST', '127.0.0.1')
LOCAL_DB_PORT = int(os.environ.get('LOCAL_DB_PORT', '3306'))
LOCAL_DB_NAME = os.environ.get('LOCAL_DB_NAME', 'local_django_db')

ENCRYPTION_SECRET = os.environ.get('BACKUP_SECRET_KEY')
if not ENCRYPTION_SECRET:
    raise ValueError("CRITICAL ERROR: BACKUP_SECRET_KEY environment variable missing!")

EXCLUDE_TABLES = {
    'auth_user', 
    'auth_group', 
    'auth_permission', 
    'auth_user_groups', 
    'auth_user_user_permissions',
    'users'
}

# --- 2. ENGINE BUILDER WITH CREDENTIAL FALLBACK ---
def get_db_engine(target="local"):
    """
    target: 'local' or 'cloud'
    Dynamically loads credentials matching the CI/CD pipeline configuration.
    """
    if target == "local":
        user, password, host, port, db_name = (
            LOCAL_DB_USER, LOCAL_DB_PASS, LOCAL_DB_HOST, LOCAL_DB_PORT, LOCAL_DB_NAME
        )
    else:
        user, password, host, port, db_name = (
            CLOUD_DB_USER, CLOUD_DB_PASS, CLOUD_DB_HOST, CLOUD_DB_PORT, CLOUD_DB_NAME
        )

    if not all([user, password, host, db_name]):
        raise ValueError(f"CRITICAL ERROR: Credentials for [{target.upper()}] DB are incomplete or missing!")

    db_uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"
    engine_options = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    
    # SSL required for Cloud/Aiven connections, omitted for local runner
    if host and host not in ['127.0.0.1', 'localhost']:
        engine_options['connect_args'] = {'ssl': {'ssl_mode': 'REQUIRED'}}
    
    return create_engine(db_uri, **engine_options), db_name

def test_connection(engine):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logging.warning(f"Connection check failed: {e}")
        return False

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
    return salt + fernet.encrypt(data_str.encode('utf-8'))

def decrypt_data(file_bytes: bytes) -> str:
    salt = file_bytes[:16]
    encrypted_bytes = file_bytes[16:]
    key = _derive_key(salt)
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_bytes).decode('utf-8')

# --- 4. EXPORT / BACKUP LOGIC ---
def export_single_db(target="local", output_filename=None):
    try:
        engine, db_name = get_db_engine(target)
        if not test_connection(engine):
            logging.warning(f"⚠️ [{target.upper()}] DB is not reachable. Skipping backup.")
            return None

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        backup_data = {}
        logging.info(f"📦 Starting Encrypted Backup for [{target.upper()}] Database: [{db_name}]...")

        with engine.connect() as conn:
            for table in tables:
                logging.info(f"  ➜ Exporting table from [{target.upper()}]: {table}")
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
            logging.info(f"✅ [{target.upper()}] Backup successfully saved to: {output_filename}")

        return encrypted_content
    except Exception as e:
        logging.error(f"❌ Failed to backup [{target.upper()}] DB: {e}")
        return None

def export_backup_sequence(filename_prefix="backup"):
    """
    1. Try Local DB Backup (Fallback to YAML Runner DB: local_django_db)
    2. Try Cloud DB Backup (Aiven Cloud DB: DB_HOST / DB_NAME)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    local_filename = f"{filename_prefix}_local_{timestamp}.enc"
    local_bytes = export_single_db(target="local", output_filename=local_filename)
    
    cloud_filename = f"{filename_prefix}_cloud_{timestamp}.enc"
    cloud_bytes = export_single_db(target="cloud", output_filename=cloud_filename)

    if not local_bytes and not cloud_bytes:
        logging.error("💥 CRITICAL: Both Local and Cloud DB backup attempts failed!")
        return False
    return True

# --- 5. HELPER FOR LATEST FILE ---
def get_latest_enc_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    enc_files = glob.glob(os.path.join(script_dir, "*.enc"))
    if not enc_files:
        return None
    return max(enc_files, key=os.path.getmtime)

# --- 6. SAFE RESTORE & SYNC LOGIC ---
def restore_to_single_db(target: str, backup_data: dict):
    try:
        engine, db_name = get_db_engine(target)
        if not test_connection(engine):
            logging.warning(f"⚠️ [{target.upper()}] DB is not reachable. Skipping restore for {target.upper()}.")
            return False, f"[{target.upper()}] DB Unreachable"

        inspector = inspect(engine)

        for table_name, rows in backup_data.items():
            if table_name in EXCLUDE_TABLES or not rows:
                continue

            if not inspector.has_table(table_name):
                msg = f"Missing table in [{target.upper()}] DB: `{table_name}`"
                logging.error(f"⛔ {msg}")
                return False, msg

            target_cols = {col['name'] for col in inspector.get_columns(table_name)}
            backup_cols = set(rows[0].keys())
            missing_cols = backup_cols - target_cols

            if missing_cols:
                msg = f"Missing columns in [{target.upper()}] DB table `{table_name}`: {missing_cols}"
                logging.error(f"⛔ {msg}")
                return False, msg

        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

            for table_name, rows in backup_data.items():
                if table_name in EXCLUDE_TABLES or not rows:
                    logging.info(f"⏩ Skipping excluded/empty table `{table_name}` on [{target.upper()}].")
                    continue

                columns = list(rows[0].keys())
                col_names_str = ", ".join([f"`{col}`" for col in columns])
                val_placeholders = ", ".join([f":{col}" for col in columns])
                update_assignments = ", ".join([f"`{col}`=VALUES(`{col}`)" for col in columns])
                
                upsert_sql = text(
                    f"INSERT INTO `{table_name}` ({col_names_str}) "
                    f"VALUES ({val_placeholders}) "
                    f"ON DUPLICATE KEY UPDATE {update_assignments}"
                )

                for row in rows:
                    for k, v in row.items():
                        if isinstance(v, str) and 'T' in v and len(v) >= 19:
                            try:
                                row[k] = v.replace('T', ' ').split('.')[0]
                            except Exception:
                                pass

                conn.execute(upsert_sql, rows)
                logging.info(f"⚡ [{target.upper()}] Synced table `{table_name}`: {len(rows)} records processed.")

            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        logging.info(f"🎉 [{target.upper()}] DB Restore Completed Successfully!")
        return True, "Success"

    except Exception as e:
        msg = f"[{target.upper()}] Restore Failed: {e}"
        logging.error(f"💥 {msg}")
        return False, msg

def execute_restore_sequence(file_bytes: bytes):
    logging.info("🛡️ Taking Pre-Restore Safety Snapshot...")
    export_backup_sequence(filename_prefix="pre_restore_safety")

    try:
        decrypted_str = decrypt_data(file_bytes)
        backup_data = json.loads(decrypted_str)
    except Exception as e:
        msg = f"Decryption Failed! Invalid Secret Key or Corrupted Backup File: {e}"
        logging.error(msg)
        return False, msg

    # 1. Restore to Local Database
    logging.info("🔄 Attempting Restore on LOCAL DB...")
    local_success, local_msg = restore_to_single_db("local", backup_data)

    # 2. Restore to Cloud Database
    logging.info("🔄 Attempting Restore on CLOUD DB...")
    cloud_success, cloud_msg = restore_to_single_db("cloud", backup_data)

    if not local_success and not cloud_success:
        return False, f"Both Restores Failed! Local: {local_msg} | Cloud: {cloud_msg}"

    return True, "Restore Sequence Executed Successfully"

# --- 7. CLI / FILE RESTORE ---
def restore_backup(backup_filepath=None):
    if not backup_filepath:
        backup_filepath = get_latest_enc_file()

    if not backup_filepath or not os.path.exists(backup_filepath):
        logging.error("❌ Error: No valid `.enc` backup file found.")
        return False, "File not found"

    logging.info(f"🔓 Processing restore file: {backup_filepath}...")
    with open(backup_filepath, "rb") as f:
        file_bytes = f.read()

    return execute_restore_sequence(file_bytes)

# --- 8. CLI INTERFACE ---
if __name__ == "__main__":
    print("--------------------------------------------------")
    print("   MySQL Local & Cloud Sync / Zero Data Loss      ")
    print("--------------------------------------------------")
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Take Backup:    python db_backup_manager.py backup")
        print("  Restore Backup: python db_backup_manager.py restore [backup_file_path]")
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "backup":
        export_backup_sequence()
    elif action == "restore":
        filepath = sys.argv[2] if len(sys.argv) >= 3 else None
        success, msg = restore_backup(filepath)
        if not success:
            sys.exit(1)
    else:
        print("❌ Invalid command! Use 'backup' or 'restore'.")
        sys.exit(1)
