import os
import json
import base64
import glob
import sys
import subprocess
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
load_dotenv()

# --- 1. ENV CONFIGURATION ---
CLOUD_DB_USER = os.environ.get('DB_USER')
CLOUD_DB_PASS = os.environ.get('DB_PASS')
CLOUD_DB_HOST = os.environ.get('DB_HOST')
CLOUD_DB_PORT = int(os.environ.get('DB_PORT', '3306'))
CLOUD_DB_NAME = os.environ.get('DB_NAME')

LOCAL_DB_USER = os.environ.get('LOCAL_DB_USER', 'root')
LOCAL_DB_PASS = os.environ.get('LOCAL_DB_PASS', 'root')
LOCAL_DB_HOST = os.environ.get('LOCAL_DB_HOST', '127.0.0.1')
LOCAL_DB_PORT = int(os.environ.get('LOCAL_DB_PORT', '3306'))
LOCAL_DB_NAME = os.environ.get('LOCAL_DB_NAME', 'local_django_db')

# Rclone Remote & Path Configuration for Google Drive
GDRIVE_REMOTE_PATH = os.environ.get('GDRIVE_REMOTE_PATH', 'gdrive_enc:db_backups')

ENCRYPTION_SECRET = os.environ.get('BACKUP_SECRET_KEY')
if not ENCRYPTION_SECRET:
    raise ValueError("CRITICAL ERROR: BACKUP_SECRET_KEY environment variable missing!")


# --- 2. ENGINE BUILDER ---
def get_db_engine(target="local"):
    if target == "local":
        user, password, host, port, db_name = (
            LOCAL_DB_USER, LOCAL_DB_PASS, LOCAL_DB_HOST, LOCAL_DB_PORT, LOCAL_DB_NAME
        )
    else:
        user, password, host, port, db_name = (
            CLOUD_DB_USER, CLOUD_DB_PASS, CLOUD_DB_HOST, CLOUD_DB_PORT, CLOUD_DB_NAME
        )

    if not all([user, password, host, db_name]):
        raise ValueError(f"Credentials for [{target.upper()}] DB are incomplete or missing!")

    db_uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"
    engine_options = {
        'pool_recycle': 280,
        'pool_pre_ping': True
    }
    
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


# --- 4. RCLONE GOOGLE DRIVE SYNC ---
def upload_to_gdrive(local_filepath):
    try:
        cmd = ["rclone", "copy", local_filepath, GDRIVE_REMOTE_PATH]
        logging.info(f"☁️ Syncing encrypted backup to Google Drive ({GDRIVE_REMOTE_PATH})...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logging.info("✅ Successfully synced to Google Drive via Rclone!")
            return True
        else:
            logging.warning(f"⚠️ Rclone upload warning: {res.stderr}")
            return False
    except Exception as e:
        logging.warning(f"⚠️ Rclone execution failed or not installed: {e}")
        return False


def download_latest_from_gdrive():
    try:
        cmd = ["rclone", "copy", GDRIVE_REMOTE_PATH, ".", "--include", "*.enc"]
        logging.info("☁️ Pulling latest encrypted backups from Google Drive...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logging.info("✅ Downloaded latest backup files from Google Drive.")
            return True
    except Exception as e:
        logging.warning(f"⚠️ Failed to pull backups from GDrive: {e}")
    return False


# --- 5. FULL SNAPSHOT EXPORT LOGIC ---
def export_single_db(target="local", output_filename=None):
    try:
        engine, db_name = get_db_engine(target)
        if not test_connection(engine):
            logging.warning(f"⚠️ [{target.upper()}] DB is not reachable. Skipping export.")
            return None

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        backup_data = {}
        logging.info(f"📸 Capturing ZERO-LOSS Point-in-Time Snapshot from [{target.upper()}] DB ({db_name})...")

        with engine.connect() as conn:
            for table in tables:
                logging.info(f"  ➜ Capturing table: {table}")
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
            logging.info(f"🔒 Point-In-Time Backup Encrypted & Saved locally: {output_filename}")
            upload_to_gdrive(output_filename)

        return encrypted_content
    except Exception as e:
        logging.error(f"❌ Failed to capture snapshot from [{target.upper()}] DB: {e}")
        return None


def export_backup_sequence():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_filename = f"snapshot_local_{timestamp}.enc"
    
    # 1. Primary Attempt: Export from Local DB
    local_bytes = export_single_db(target="local", output_filename=local_filename)
    if local_bytes:
        return True

    # 2. Fallback Attempt: Export from Cloud DB if Local Unavailable
    logging.info("⚠️ Local DB snapshot failed. Trying Cloud DB snapshot...")
    cloud_filename = f"snapshot_cloud_{timestamp}.enc"
    cloud_bytes = export_single_db(target="cloud", output_filename=cloud_filename)

    if not cloud_bytes:
        logging.error("💥 CRITICAL: Both Local and Cloud DB Backup failed!")
        return False
    return True


# --- 6. EXACT POINT-IN-TIME RESTORE LOGIC ---
def get_latest_enc_file():
    download_latest_from_gdrive()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    enc_files = glob.glob(os.path.join(script_dir, "*.enc"))
    if not enc_files:
        return None
    return max(enc_files, key=os.path.getmtime)


def restore_exact_snapshot_to_db(target: str, backup_data: dict):
    """
    TRUNCATES tables to remove all current post-backup noise/extra rows,
    then INSERTS the exact backup state.
    """
    try:
        engine, db_name = get_db_engine(target)
        if not test_connection(engine):
            logging.warning(f"⚠️ [{target.upper()}] DB is not reachable.")
            return False, f"[{target.upper()}] DB Unreachable"

        logging.info(f"🧹 Preparing [{target.upper()}] DB for exact state recovery...")

        with engine.begin() as conn:
            # Disable FK checks to allow clean Truncate & Bulk Restore
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

            # Step A: TRUNCATE ALL TABLES present in the backup snapshot
            for table_name in backup_data.keys():
                logging.info(f"  ➜ Wiping table `{table_name}` on [{target.upper()}]...")
                conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))

            # Step B: INSERT EXACT SNAPSHOT DATA
            for table_name, rows in backup_data.items():
                if not rows:
                    continue

                columns = list(rows[0].keys())
                col_names_str = ", ".join([f"`{col}`" for col in columns])
                val_placeholders = ", ".join([f":{col}" for col in columns])
                
                insert_sql = text(f"INSERT INTO `{table_name}` ({col_names_str}) VALUES ({val_placeholders})")

                for row in rows:
                    for k, v in row.items():
                        if isinstance(v, str) and 'T' in v and len(v) >= 19:
                            try:
                                row[k] = v.replace('T', ' ').split('.')[0]
                            except Exception:
                                pass

                conn.execute(insert_sql, rows)
                logging.info(f"  ✅ Restored `{table_name}` ({len(rows)} records) to exact snapshot state.")

            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        logging.info(f"🎉 [{target.upper()}] DB successfully restored to exact snapshot time!")
        return True, "Success"

    except Exception as e:
        msg = f"[{target.upper()}] Exact Restore Failed: {e}"
        logging.error(f"💥 {msg}")
        return False, msg


def execute_restore_sequence(file_bytes: bytes):
    try:
        decrypted_str = decrypt_data(file_bytes)
        backup_data = json.loads(decrypted_str)
    except Exception as e:
        msg = f"Decryption Failed! Invalid Secret Key or Corrupted Backup File: {e}"
        logging.error(msg)
        return False, msg

    # --- ROUTING Strategy: Try LOCAL DB First. If Local Fails/Unavailable -> Fallback to CLOUD DB ---
    logging.info("🔄 Phase 1: Restoring exact snapshot to LOCAL DB...")
    local_success, local_msg = restore_exact_snapshot_to_db("local", backup_data)

    if local_success:
        logging.info("🎯 Local DB restore successful!")
        return True, "Local DB Restored Successfully"

    logging.warning(f"⚠️ LOCAL DB restore failed ({local_msg}). Triggering FAILOVER to CLOUD DB...")
    logging.info("🔄 Phase 2: Restoring exact snapshot to CLOUD DB...")
    cloud_success, cloud_msg = restore_exact_snapshot_to_db("cloud", backup_data)

    if cloud_success:
        logging.info("🎯 Cloud DB restore successful via Fallback!")
        return True, "Cloud DB Restored Successfully via Failover"

    return False, f"Both Restores Failed! Local Error: {local_msg} | Cloud Error: {cloud_msg}"


# --- 7. CLI EXECUTION ---
def restore_backup(backup_filepath=None):
    if not backup_filepath:
        backup_filepath = get_latest_enc_file()

    if not backup_filepath or not os.path.exists(backup_filepath):
        logging.error("❌ Error: No valid `.enc` backup file found locally or on Google Drive.")
        return False, "File not found"

    logging.info(f"🔓 Decrypting and recovering snapshot from: {backup_filepath}...")
    with open(backup_filepath, "rb") as f:
        file_bytes = f.read()

    return execute_restore_sequence(file_bytes)


if __name__ == "__main__":
    print("----------------------------------------------------------")
    print("  MySQL True Snapshot Backup & Failover Recovery System  ")
    print("----------------------------------------------------------")
    
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
