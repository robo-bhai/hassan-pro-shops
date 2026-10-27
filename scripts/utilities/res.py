import os
import json
import base64
import glob
from sqlalchemy import create_engine, inspect, text
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MYSQL_USER = os.environ.get('DB_USER')
MYSQL_PASSWORD = os.environ.get('DB_PASS')
MYSQL_HOST = os.environ.get('DB_HOST')
MYSQL_PORT = os.environ.get('DB_PORT', '3306')
MYSQL_DB = os.environ.get('DB_NAME')
ENCRYPTION_SECRET = os.environ.get('BACKUP_SECRET_KEY')

EXCLUDE_TABLES = {
    'auth_user', 
    'auth_group', 
    'auth_permission', 
    'auth_user_groups', 
    'auth_user_user_permissions',
    'users'
}

def get_latest_enc_file():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    enc_files = glob.glob(os.path.join(script_dir, "*.enc"))
    if not enc_files:
        return None
    return max(enc_files, key=os.path.getmtime)

def get_db_engine():
    db_uri = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    engine_options = {'pool_recycle': 280, 'pool_pre_ping': True}
    if MYSQL_HOST and MYSQL_HOST != '127.0.0.1':
        engine_options['connect_args'] = {'ssl': {'ssl_mode': 'REQUIRED'}}
    return create_engine(db_uri, **engine_options)

def _derive_key(salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(ENCRYPTION_SECRET.encode()))

def decrypt_data(file_bytes: bytes) -> str:
    salt = file_bytes[:16]
    encrypted_bytes = file_bytes[16:]
    key = _derive_key(salt)
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_bytes).decode('utf-8')

def execute_restore_from_bytes(file_bytes: bytes):
    try:
        decrypted_str = decrypt_data(file_bytes)
        backup_data = json.loads(decrypted_str)
    except Exception as e:
        return False, f"Decryption Failed! Invalid Secret Key or Corrupted File. Details: {e}"

    engine = get_db_engine()
    inspector = inspect(engine)

    schema_is_valid = True
    missing_tables = []
    missing_columns = {}

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
        msg = f"Schema Mismatch Detected! Missing tables: {missing_tables}, Missing columns: {missing_columns}"
        return False, msg

    try:
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            for table_name, rows in backup_data.items():
                if table_name in EXCLUDE_TABLES or not rows:
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

            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        return True, "Full Restore Completed Successfully!"
    except Exception as e:
        return False, f"Restore Failed! Details: {e}"

def execute_hardcoded_restore():
    backup_file_path = get_latest_enc_file()
    if not backup_file_path or not os.path.exists(backup_file_path):
        print("❌ Directory mein koi `.enc` backup file nahi mili!")
        return

    with open(backup_file_path, "rb") as f:
        file_bytes = f.read()

    status, msg = execute_restore_from_bytes(file_bytes)
    print(msg)

if __name__ == "__main__":
    execute_hardcoded_restore()
