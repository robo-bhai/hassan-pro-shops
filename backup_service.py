"""
app/backup_service.py
=====================
Professional backup engine for the ERP.

Features
--------
* Consistent online backup (SQLite backup API / mysqldump --single-transaction / pg_dump)
* gzip compression (streamed, low memory)
* SHA-256 checksums + JSON manifest for every backup
* Automatic verification after every backup (integrity_check + hash re-read)
* media/ folder backup (tar.gz)
* GFS retention (daily / weekly / monthly) - local AND cloud
* Cloud upload with rclone, verified by size
* Single-run lock (two backups can never run together)
* Safe restore: verify first -> safety copy of current DB -> restore
* Health status (last success / failure / age) + e-mail on failure
* No shell=True anywhere, passwords never on the command line

Everything is optional-configurable in settings.py (see BACKUP_SETUP.md).
"""
import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("app.backup")

STEPS = {
    1: "Database snapshot",
    2: "Compress",
    3: "Verify backup",
    4: "Media files",
    5: "Cloud upload",
    6: "Retention cleanup",
}
TOTAL_STEPS = 6
CHUNK = 1024 * 1024
STALE_LOCK_SECONDS = 6 * 3600


class BackupError(Exception):
    pass


# --------------------------------------------------------------------------
# Settings helpers
# --------------------------------------------------------------------------
def _cfg(name, default=None):
    return getattr(settings, name, default)


def backup_dir() -> Path:
    d = Path(_cfg("BACKUP_DIR", Path(settings.BASE_DIR) / "backups"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _progress_file() -> Path:
    return Path(_cfg("BACKUP_PROGRESS_FILE", backup_dir() / ".progress.json"))


def _status_file() -> Path:
    return backup_dir() / ".status.json"


def retention():
    r = {"daily": 7, "weekly": 4, "monthly": 12, "recent_hours": 24}
    r.update(_cfg("BACKUP_KEEP", {}) or {})
    return r


def cloud_enabled() -> bool:
    return bool(_cfg("RCLONE_ENABLED", False))


def _remote():
    name = _cfg("RCLONE_REMOTE_NAME", "gdrive")
    folder = _cfg("RCLONE_REMOTE_DIR", "ERPBackups")
    return name, folder, f"{name}:{folder}"


def db_conf():
    return settings.DATABASES["default"]


def db_kind() -> str:
    engine = db_conf()["ENGINE"].lower()
    if "sqlite" in engine:
        return "sqlite"
    if "mysql" in engine or "mariadb" in engine:
        return "mysql"
    if "postgres" in engine:
        return "postgres"
    raise BackupError(f"Unsupported database engine: {engine}")


# --------------------------------------------------------------------------
# Small utilities
# --------------------------------------------------------------------------
def _atomic_write_json(path: Path, data: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def update_progress(step, message, status="in_progress", sub=0.0):
    """Write progress in the same JSON shape the existing UI already reads."""
    current = max(0.0, (step - 1) + sub) if step else 0
    data = {
        "step": step,
        "total": TOTAL_STEPS,
        "current": round(current, 2),
        "percentage": round(min(100.0, current / TOTAL_STEPS * 100), 1),
        "message": message,
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "step_name": STEPS.get(step, ""),
    }
    if status == "completed":
        data["percentage"] = 100.0
        data["current"] = TOTAL_STEPS
    try:
        _atomic_write_json(_progress_file(), data)
    except Exception as e:  # progress must never break a backup
        logger.warning("progress write failed: %s", e)


def read_progress():
    try:
        return json.loads(_progress_file().read_text(encoding="utf-8"))
    except Exception:
        return {"step": 0, "percentage": 0, "message": "No backup in progress", "status": "idle"}


def sha256_file(path, chunk=CHUNK) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class BackupLock:
    """Cross-process lock (O_EXCL lockfile with stale detection)."""

    def __init__(self):
        self.path = backup_dir() / ".backup.lock"

    def __enter__(self):
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                age = time.time() - self.path.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    logger.warning("Removing stale backup lock (%.0fs old)", age)
                    self.path.unlink(missing_ok=True)
                    continue
                raise BackupError("Another backup/restore is already running.")
        raise BackupError("Could not acquire backup lock.")

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Database snapshot / restore per engine
# --------------------------------------------------------------------------
def _snapshot_sqlite(dest: Path):
    src_path = str(db_conf()["NAME"])
    if not os.path.exists(src_path):
        raise BackupError(f"SQLite file not found: {src_path}")
    src = sqlite3.connect(src_path, timeout=60)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)  # consistent even while the site is writing
        dst.commit()
        row = dst.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise BackupError(f"SQLite integrity check failed: {row}")
    finally:
        dst.close()
        src.close()


def _mysql_env_args():
    c = db_conf()
    args = ["-h", str(c.get("HOST") or "localhost"), "-P", str(c.get("PORT") or 3306),
            "-u", str(c["USER"])]
    env = dict(os.environ, MYSQL_PWD=str(c.get("PASSWORD", "")))
    return args, env


def _snapshot_dump(dest: Path):
    """mysql / postgres -> plain .sql file."""
    c = db_conf()
    kind = db_kind()
    if kind == "mysql":
        extra, env = _mysql_env_args()
        cmd = ["mysqldump", *extra, "--single-transaction", "--quick", "--routines",
               "--triggers", "--default-character-set=utf8mb4", c["NAME"]]
    else:
        env = dict(os.environ, PGPASSWORD=str(c.get("PASSWORD", "")))
        cmd = ["pg_dump", "-h", str(c.get("HOST") or "localhost"), "-p", str(c.get("PORT") or 5432),
               "-U", str(c["USER"]), "--no-owner", "--clean", "--if-exists", c["NAME"]]
    with open(dest, "wb") as out:
        proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, env=env, timeout=3600)
    if proc.returncode != 0:
        raise BackupError(f"{cmd[0]} failed: {proc.stderr.decode(errors='replace')[:400]}")
    if dest.stat().st_size < 100:
        raise BackupError("Dump file is suspiciously small.")


def _restore_sqlite(raw: Path):
    chk = sqlite3.connect(str(raw))
    try:
        row = chk.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            raise BackupError(f"Backup file is corrupt: {row}")
    finally:
        chk.close()
    from django.db import connections
    connections.close_all()
    src = sqlite3.connect(str(raw))
    dst = sqlite3.connect(str(db_conf()["NAME"]), timeout=60)
    try:
        src.backup(dst)  # overwrites live DB safely, no file swapping
        dst.commit()
    finally:
        dst.close()
        src.close()


def _restore_dump(raw: Path):
    c = db_conf()
    if db_kind() == "mysql":
        extra, env = _mysql_env_args()
        cmd = ["mysql", *extra, c["NAME"]]
    else:
        env = dict(os.environ, PGPASSWORD=str(c.get("PASSWORD", "")))
        cmd = ["psql", "-h", str(c.get("HOST") or "localhost"), "-p", str(c.get("PORT") or 5432),
               "-U", str(c["USER"]), "-v", "ON_ERROR_STOP=1", c["NAME"]]
    from django.db import connections
    connections.close_all()
    with open(raw, "rb") as inp:
        proc = subprocess.run(cmd, stdin=inp, stderr=subprocess.PIPE, env=env, timeout=7200)
    if proc.returncode != 0:
        raise BackupError(f"Restore failed: {proc.stderr.decode(errors='replace')[:400]}")


# --------------------------------------------------------------------------
# Compress / verify
# --------------------------------------------------------------------------
def _gzip_file(src: Path, dst: Path, progress=None):
    """Compress and return sha256 of the *uncompressed* data."""
    h = hashlib.sha256()
    total = max(src.stat().st_size, 1)
    done = 0
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        for block in iter(lambda: fin.read(CHUNK), b""):
            h.update(block)
            fout.write(block)
            done += len(block)
            if progress:
                progress(done / total)
    return h.hexdigest()


def _gunzip_hash(path: Path):
    h = hashlib.sha256()
    with gzip.open(path, "rb") as f:  # raises on CRC error => detects corruption
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _open_to_raw(path: Path, workdir: Path) -> Path:
    """backup file (.gz) -> raw database file inside workdir."""
    cur = Path(path)
    raw = workdir / "restore.raw"
    if cur.name.endswith(".gz") or cur.suffix == ".gz":
        with gzip.open(cur, "rb") as fin, open(raw, "wb") as fout:
            shutil.copyfileobj(fin, fout, CHUNK)
    else:
        shutil.copyfile(cur, raw)
    return raw


# --------------------------------------------------------------------------
# Listing / retention
# --------------------------------------------------------------------------
def _is_main(name: str) -> bool:
    return name.startswith("backup_") and (
        name.endswith((".sqlite3.gz", ".sql.gz", ".sqlite3")))


def _stamp(name: str):
    try:
        return datetime.strptime(name.split("_", 1)[1][:15], "%Y%m%d_%H%M%S")
    except Exception:
        return None


def _base(name: str) -> str:
    """backup_20250101_120000"""
    return name[:22] if name.startswith("backup_") else name


def list_backups():
    items = []
    for p in sorted(backup_dir().iterdir(), reverse=True):
        if p.is_file() and _is_main(p.name):
            st = p.stat()
            manifest = p.with_name(_base(p.name) + ".json")
            verified = None
            if manifest.exists():
                try:
                    verified = json.loads(manifest.read_text()).get("verified")
                except Exception:
                    pass
            items.append({
                "name": p.name,
                "size": st.st_size,
                "size_display": human_size(st.st_size),
                "size_mb": round(st.st_size / 1048576, 2),
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "is_compressed": p.name.endswith(".gz"),
                "encrypted": False,
                "verified": verified,
                "path": str(p),
            })
    return items


def select_to_delete(entries, keep=None, now=None):
    """
    GFS retention. `entries` = list of (name, datetime). Returns names to delete.
    Keeps: newest N daily (1/day), N weekly (1/ISO week), N monthly (1/month).
    Everything newer than `recent_hours` (default 24h) is always kept, so a manual
    backup taken before a risky change is never removed by the next run.
    The most recent backup is always kept.
    """
    now = now or datetime.now()
    keep = keep or retention()
    entries = sorted(entries, key=lambda e: e[1], reverse=True)
    if not entries:
        return []
    keepers = {entries[0][0]}
    cutoff = now - timedelta(hours=keep.get("recent_hours", 24))
    keepers.update(n for n, dt in entries if dt >= cutoff)
    seen = {"daily": set(), "weekly": set(), "monthly": set()}
    for name, dt in entries:  # newest first => first of each bucket wins
        d = dt.strftime("%Y-%m-%d")
        w = "%d-W%02d" % dt.isocalendar()[:2]
        m = dt.strftime("%Y-%m")
        if d not in seen["daily"] and len(seen["daily"]) < keep["daily"]:
            seen["daily"].add(d); keepers.add(name)
        if w not in seen["weekly"] and len(seen["weekly"]) < keep["weekly"]:
            seen["weekly"].add(w); keepers.add(name)
        if m not in seen["monthly"] and len(seen["monthly"]) < keep["monthly"]:
            seen["monthly"].add(m); keepers.add(name)
    return [n for n, _ in entries if n not in keepers]


def prune_local():
    entries = []
    for p in backup_dir().iterdir():
        if p.is_file() and _is_main(p.name) and _stamp(p.name):
            entries.append((p.name, _stamp(p.name)))
    deleted = []
    for name in select_to_delete(entries):
        base = _base(name)
        for p in backup_dir().iterdir():
            if p.is_file() and p.name.startswith(base):
                p.unlink(missing_ok=True)
        deleted.append(name)
    return deleted


# --------------------------------------------------------------------------
# rclone (cloud)
# --------------------------------------------------------------------------
def _rclone(args, timeout=1800):
    return subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=timeout)


def rclone_status():
    if not shutil.which("rclone"):
        return {"rclone_installed": False, "remote_configured": False,
                "message": "rclone is not installed."}
    name, folder, path = _remote()
    r = _rclone(["lsd", f"{name}:"], timeout=30)
    ok = r.returncode == 0
    return {"rclone_installed": True, "remote_configured": ok, "remote_name": name,
            "remote_dir": folder,
            "message": "Cloud ready." if ok else "Remote not configured. Run: rclone config"}


def cloud_list():
    name, folder, path = _remote()
    r = _rclone(["lsjson", path], timeout=60)
    if r.returncode != 0:
        raise BackupError(f"rclone list failed: {r.stderr[:300]}")
    out = []
    for f in json.loads(r.stdout or "[]"):
        if not f.get("IsDir") and _is_main(f["Name"]):
            out.append({"name": f["Name"], "size": f.get("Size", 0),
                        "size_display": human_size(f.get("Size", 0)),
                        "modified": f.get("ModTime", "")[:19].replace("T", " ")})
    return sorted(out, key=lambda x: x["modified"], reverse=True)


def cloud_upload(path: Path):
    """Upload one file and verify the size on the remote side."""
    if not shutil.which("rclone"):
        raise BackupError("rclone is not installed.")
    name, folder, remote = _remote()
    path = Path(path)
    r = _rclone(["copyto", str(path), f"{remote}/{path.name}", "--retries", "3",
                 "--low-level-retries", "5", "--checksum"])
    if r.returncode != 0:
        raise BackupError(f"Upload failed: {r.stderr[:300]}")
    chk = _rclone(["lsjson", f"{remote}/{path.name}"], timeout=60)
    try:
        size = json.loads(chk.stdout)[0]["Size"]
    except Exception:
        raise BackupError("Could not verify uploaded file on the remote.")
    if size != path.stat().st_size:
        raise BackupError(f"Remote size mismatch ({size} != {path.stat().st_size}).")
    return True


def cloud_prune():
    name, folder, remote = _remote()
    entries = [(f["name"], _stamp(f["name"])) for f in cloud_list() if _stamp(f["name"])]
    deleted = []
    for fname in select_to_delete(entries):
        base = _base(fname)
        r = _rclone(["lsjson", remote], timeout=60)
        for f in json.loads(r.stdout or "[]"):
            if f["Name"].startswith(base):
                _rclone(["deletefile", f"{remote}/{f['Name']}"], timeout=60)
        deleted.append(fname)
    return deleted


def cloud_download(filename: str, dest_dir: Path) -> Path:
    name, folder, remote = _remote()
    dest = Path(dest_dir) / filename
    r = _rclone(["copyto", f"{remote}/{filename}", str(dest)], timeout=3600)
    if r.returncode != 0 or not dest.exists():
        raise BackupError(f"Download failed: {r.stderr[:300]}")
    return dest


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def create_backup(upload=None, include_media=None, trigger="manual"):
    """Run a full backup. Returns the manifest dict. Raises BackupError."""
    upload = cloud_enabled() if upload is None else (upload and cloud_enabled())
    include_media = _cfg("BACKUP_INCLUDE_MEDIA", True) if include_media is None else include_media
    started = time.time()

    with BackupLock():
        try:
            return _run_backup(upload, include_media, trigger, started)
        except Exception as e:
            msg = str(e) or e.__class__.__name__
            update_progress(0, f"Backup failed: {msg}", status="failed")
            _record_status(False, msg)
            _notify_failure(msg)
            logger.exception("Backup failed")
            if isinstance(e, BackupError):
                raise
            raise BackupError(msg) from e


def _run_backup(upload, include_media, trigger, started):
    kind = db_kind()
    out_dir = backup_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"backup_{ts}"
    ext = ".sqlite3" if kind == "sqlite" else ".sql"
    manifest = {"name": base, "created": datetime.now().isoformat(), "trigger": trigger,
                "engine": kind, "encrypted": False, "files": {}, "cloud": False,
                "verified": False}

    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".tmp_") as tmp:
        tmp = Path(tmp)
        raw = tmp / f"raw{ext}"

        update_progress(1, "Taking consistent database snapshot...")
        (_snapshot_sqlite if kind == "sqlite" else _snapshot_dump)(raw)
        raw_size = raw.stat().st_size

        update_progress(2, "Compressing...", sub=0.0)
        gz = tmp / f"{base}{ext}.gz"
        raw_hash = _gzip_file(raw, gz, lambda f: update_progress(
            2, f"Compressing... {f * 100:.0f}%", sub=f))
        final = gz

        update_progress(3, "Verifying backup...")
        verify_dir = tmp / "verify"
        verify_dir.mkdir()
        check_raw = _open_to_raw(final, verify_dir)  # gunzip
        if sha256_file(check_raw) != raw_hash:
            raise BackupError("Verification failed: restored data does not match snapshot.")
        if kind == "sqlite":
            c = sqlite3.connect(str(check_raw))
            try:
                if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("Verification failed: integrity_check.")
                tables = c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                manifest["tables"] = tables
            finally:
                c.close()
        manifest.update(verified=True, raw_size=raw_size, raw_sha256=raw_hash)

        # move into place (atomic rename on the same filesystem)
        dest_main = out_dir / final.name
        shutil.move(str(final), dest_main)
        manifest["files"]["database"] = {"name": dest_main.name, "size": dest_main.stat().st_size,
                                         "sha256": sha256_file(dest_main)}

        update_progress(4, "Backing up media files...")
        media_root = Path(getattr(settings, "MEDIA_ROOT", "") or "")
        dest_media = None
        if include_media and media_root.is_dir() and any(media_root.iterdir()):
            media_tar = tmp / f"{base}.media.tar.gz"
            with tarfile.open(media_tar, "w:gz") as tar:
                tar.add(media_root, arcname="media")
            dest_media = out_dir / media_tar.name
            shutil.move(str(media_tar), dest_media)
            manifest["files"]["media"] = {"name": dest_media.name, "size": dest_media.stat().st_size,
                                          "sha256": sha256_file(dest_media)}

    manifest_path = out_dir / f"{base}.json"
    _atomic_write_json(manifest_path, manifest)

    if upload:
        update_progress(5, "Uploading to cloud...")
        try:
            for p in (dest_main, dest_media, manifest_path):
                if p:
                    cloud_upload(p)
            manifest["cloud"] = True
            _atomic_write_json(manifest_path, manifest)
        except Exception as e:
            manifest["cloud_error"] = str(e)
            _atomic_write_json(manifest_path, manifest)
            logger.error("Cloud upload failed: %s", e)
            _notify_failure(f"Local backup OK but cloud upload FAILED: {e}")
    else:
        update_progress(5, "Cloud upload skipped.")

    update_progress(6, "Applying retention policy...")
    pruned = prune_local()
    if upload and manifest["cloud"]:
        try:
            pruned += cloud_prune()
        except Exception as e:
            logger.warning("Cloud prune failed: %s", e)

    manifest["duration_sec"] = round(time.time() - started, 1)
    manifest["pruned"] = pruned
    _atomic_write_json(manifest_path, manifest)
    size = manifest["files"]["database"]["size"]
    msg = f"Backup complete ({human_size(size)}, verified" + (", cloud OK)" if manifest["cloud"] else ")")
    if upload and not manifest["cloud"]:
        msg = f"Backup complete and verified, but CLOUD UPLOAD FAILED ({human_size(size)})"
    update_progress(6, msg, status="completed")
    _record_status(True, msg, manifest)
    logger.info(msg)
    manifest["file"] = str(dest_main)
    manifest["size_mb"] = round(size / 1048576, 2)
    manifest["timestamp"] = ts
    manifest["message"] = msg
    return manifest


def restore_backup(path, make_safety_copy=True):
    """Restore the database from a local backup file. Returns safety-copy path."""
    path = Path(path)
    if not path.is_file():
        raise BackupError("Backup file not found.")
    kind = db_kind()
    with BackupLock():
        with tempfile.TemporaryDirectory(dir=backup_dir(), prefix=".tmp_restore_") as tmp:
            tmp = Path(tmp)
            raw = _open_to_raw(path, tmp)  # gunzip/hash-check by CRC
            manifest = path.with_name(_base(path.name) + ".json")
            if manifest.exists():
                try:
                    expect = json.loads(manifest.read_text()).get("raw_sha256")
                    if expect and sha256_file(raw) != expect:
                        raise BackupError("Backup checksum mismatch - file is damaged.")
                except json.JSONDecodeError:
                    pass
            safety = None
            if make_safety_copy:
                safety_dir = backup_dir() / "safety"
                safety_dir.mkdir(exist_ok=True)
                safety = safety_dir / f"before_restore_{datetime.now():%Y%m%d_%H%M%S}"
                if kind == "sqlite":
                    safety = safety.with_suffix(".sqlite3")
                    _snapshot_sqlite(safety)
                else:
                    safety = safety.with_suffix(".sql")
                    _snapshot_dump(safety)
            (_restore_sqlite if kind == "sqlite" else _restore_dump)(raw)
    logger.warning("Database restored from %s (safety copy: %s)", path.name, safety)
    return str(safety) if safety else None


def restore_media(db_backup_path):
    """Restore the media/ folder that belongs to a database backup (same timestamp). Merges, never deletes."""
    db_backup_path = Path(db_backup_path)
    media_tar = db_backup_path.with_name(_base(db_backup_path.name) + ".media.tar.gz")
    if not media_tar.is_file():
        raise BackupError("No media backup found for this database backup.")
    media_root = Path(getattr(settings, "MEDIA_ROOT", "") or "")
    if not str(media_root):
        raise BackupError("MEDIA_ROOT is not set.")
    dest = media_root.resolve()
    with BackupLock():
        with tarfile.open(media_tar, "r:gz") as tar:
            for m in tar.getmembers():
                if m.issym() or m.islnk() or m.isdev():
                    raise BackupError(f"Unsafe entry in media archive: {m.name}")
                parts = Path(m.name).parts
                if not parts or parts[0] != "media" or ".." in parts:
                    raise BackupError(f"Unsafe path in media archive: {m.name}")
                target = (dest.parent / m.name).resolve()
                if not str(target).startswith(str(dest)):
                    raise BackupError(f"Unsafe path in media archive: {m.name}")
            dest.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=backup_dir(), prefix=".tmp_media_") as tmp:
                tar.extractall(tmp)
                shutil.copytree(Path(tmp) / "media", dest, dirs_exist_ok=True)
    return str(media_tar)


def verify_backup(path):
    """Re-verify an existing backup file. Returns (ok, message)."""
    path = Path(path)
    try:
        with tempfile.TemporaryDirectory(dir=backup_dir(), prefix=".tmp_verify_") as tmp:
            raw = _open_to_raw(path, Path(tmp))
            if path.name.endswith((".sqlite3", ".sqlite3.gz")):
                c = sqlite3.connect(str(raw))
                try:
                    r = c.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    c.close()
                if r != "ok":
                    return False, f"integrity_check: {r}"
            mf = path.with_name(_base(path.name) + ".json")
            if mf.exists():
                expect = json.loads(mf.read_text()).get("raw_sha256")
                if expect and sha256_file(raw) != expect:
                    return False, "checksum mismatch"
        return True, "OK"
    except Exception as e:
        return False, str(e)


def resolve_local(filename: str) -> Path:
    """Safe filename -> path inside BACKUP_DIR (whitelist, no traversal)."""
    names = {b["name"]: b["path"] for b in list_backups()}
    if filename not in names:
        raise BackupError("Backup not found.")
    return Path(names[filename])


# --------------------------------------------------------------------------
# Health / status / alerts
# --------------------------------------------------------------------------
def _record_status(ok, message, manifest=None):
    try:
        cur = json.loads(_status_file().read_text())
    except Exception:
        cur = {}
    now = datetime.now().isoformat()
    if ok:
        cur.update(last_success=now, last_message=message,
                   last_file=(manifest or {}).get("name"), consecutive_failures=0)
    else:
        cur.update(last_failure=now, last_error=message,
                   consecutive_failures=cur.get("consecutive_failures", 0) + 1)
    try:
        _atomic_write_json(_status_file(), cur)
    except Exception:
        pass


def health():
    """Used by dashboards / monitoring."""
    try:
        st = json.loads(_status_file().read_text())
    except Exception:
        st = {}
    max_age = _cfg("BACKUP_MAX_AGE_HOURS", 26)
    age = None
    if st.get("last_success"):
        age = (datetime.now() - datetime.fromisoformat(st["last_success"])).total_seconds() / 3600
    healthy = age is not None and age <= max_age and st.get("consecutive_failures", 0) == 0
    return {"healthy": healthy, "age_hours": None if age is None else round(age, 1),
            "max_age_hours": max_age, **st}


def _notify_failure(message):
    recipients = _cfg("BACKUP_NOTIFY_EMAIL", None)
    if not recipients:
        return
    try:
        from django.core.mail import send_mail
        send_mail("[ERP] BACKUP PROBLEM", message,
                  _cfg("DEFAULT_FROM_EMAIL", None), list(recipients), fail_silently=True)
    except Exception as e:
        logger.warning("Could not send failure e-mail: %s", e)
