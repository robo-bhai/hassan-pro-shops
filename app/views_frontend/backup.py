"""Frontend views: backup (drop-in replacement, powered by app.backup_service).

Same function names / JSON shapes as the old file, so urls.py and
database_backup.html keep working. Differences:
  * every endpoint is SUPERUSER only (old ones allowed staff / anyone)
  * file names are whitelisted against the real backup folder (no path tricks)
  * no shell=True, no raw file copy over a live DB
  * restore verifies the backup and makes a safety copy first
"""
import json
import logging
import os
import subprocess
import threading
import urllib.request
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from urllib.parse import unquote

from .. import backup_service as bs
from ..models import CompanyInfo

logger = logging.getLogger("app.backup")

ALLOWED_UPLOAD_EXT = (".sqlite3.gz", ".sql.gz", ".sqlite3")
MAX_UPLOAD_MB = 2048


def superuser_json(view):
    """Login + superuser required; JSON error instead of a redirect."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        u = request.user
        if not u.is_authenticated:
            return JsonResponse({"success": False, "message": "Login required."}, status=401)
        if not u.is_superuser:
            return JsonResponse({"success": False, "message": "Superuser only."}, status=403)
        return view(request, *args, **kwargs)
    return wrapper


def superuser_page(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "Access denied! Only superuser can access backup.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return wrapper


def _audit(request, what):
    logger.warning("BACKUP AUDIT user=%s ip=%s action=%s", request.user,
                   request.META.get("REMOTE_ADDR"), what)


def _hist(request, action, file="", status="ok", detail=""):
    """One entry in the History table (shown on the page)."""
    bs.log_event(action, file=file, status=status, detail=detail,
                 user=str(getattr(request, "user", "") or ""),
                 ip=request.META.get("REMOTE_ADDR", ""))


# ---------------------------------------------------------------- main page
@superuser_page
def database_backup_view(request):
    if request.method == "GET" and request.GET.get("history"):
        try:
            limit = max(1, min(int(request.GET.get("limit", 100)), 500))
        except ValueError:
            limit = 100
        return JsonResponse({"success": True, "events": bs.read_history(limit)})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_retention":
            before = bs.retention()
            try:
                values = {k: request.POST.get(k) for k in bs.RETENTION_LIMITS
                          if request.POST.get(k) not in (None, "")}
                after = bs.set_retention(values, request.user)
            except bs.BackupError as e:
                return JsonResponse({"success": False, "message": str(e)})
            changes = ", ".join(f"{k} {before[k]}->{after[k]}" for k in after
                                if before.get(k) != after[k]) or "no change"
            _hist(request, "retention_change", detail=changes)
            return JsonResponse({"success": True, "message": "Retention policy saved.",
                                 "retention": after, "preview": bs.preview_prune()})
        if action == "apply_retention":
            try:
                local = bs.prune_local()
                cloud = []
                if bs.cloud_enabled():
                    try:
                        cloud = bs.cloud_prune()
                    except Exception as e:
                        logger.warning("Cloud prune failed: %s", e)
                _hist(request, "cleanup",
                      detail=f"{len(local)} local, {len(cloud)} Drive removed (retention policy)")
                msg = f"Removed {len(local)} old local backup(s)" + (f" and {len(cloud)} from Drive." if cloud else ".")
                return JsonResponse({"success": True, "message": msg, "preview": bs.preview_prune()})
            except Exception as e:
                _hist(request, "cleanup", status="failed", detail=str(e))
                return JsonResponse({"success": False, "message": f"Cleanup failed: {e}"})
        if action in ("encrypted_backup", "json_backup", "sqlite_backup", "backup"):
            try:
                m = bs.create_backup(trigger=f"web:{request.user}")
                messages.success(request, f"✅ {m['message']}")
            except bs.BackupError as e:
                messages.error(request, f"❌ Backup failed: {e}")
        elif action == "restore_latest":
            files = bs.list_backups()
            if not files:
                messages.error(request, "❌ No backup found.")
            else:
                try:
                    _audit(request, f"restore_latest {files[0]['name']}")
                    safety = bs.restore_backup(files[0]["path"])
                    _hist(request, "restore", files[0]["name"], detail=f"latest | safety copy: {safety}")
                    messages.success(request, f"🎉 Restored {files[0]['name']}. Safety copy: {safety}")
                except bs.BackupError as e:
                    _hist(request, "restore", files[0]["name"], "failed", str(e))
                    messages.error(request, f"❌ Restore failed: {e}")
        elif action == "restore_upload" and request.FILES.get("backup_file"):
            try:
                path = _save_upload(request.FILES["backup_file"])
                _audit(request, f"restore_upload {path.name}")
                safety = bs.restore_backup(path)
                _hist(request, "restore", path.name, detail=f"uploaded file | safety copy: {safety}")
                messages.success(request, f"🎉 Restored. Old DB saved as safety copy: {safety}")
            except bs.BackupError as e:
                _hist(request, "restore", "", "failed", str(e))
                messages.error(request, f"❌ Restore failed: {e}")
        return redirect("database_backup")

    files = bs.list_backups()
    return render(request, "database_backup.html", {
        "company_name": CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else "ERP System",
        "backup_dir": str(bs.backup_dir()),
        "backup_files": [f["name"] for f in files],
        "file_sizes": {f["name"]: f["size_display"] for f in files},
        "file_dates": {f["name"]: f["modified"] for f in files},
        "db_name": os.path.basename(str(bs.db_conf().get("NAME", ""))),
        "backup_health": bs.health(),
        "backup_retention": bs.retention(),
        "retention_preview": bs.preview_prune(),
    })


def _save_upload(f):
    name = os.path.basename(f.name)
    if not name.endswith(ALLOWED_UPLOAD_EXT):
        raise bs.BackupError("Invalid file type. Allowed: " + ", ".join(ALLOWED_UPLOAD_EXT))
    if f.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise bs.BackupError(f"File too large (max {MAX_UPLOAD_MB} MB).")
    ext = next(e for e in sorted(ALLOWED_UPLOAD_EXT, key=len, reverse=True) if name.endswith(e))
    # new name: <Company>_<date>_<day>_<time>_Uploaded  (retention/listing understands this)
    dest = bs.backup_dir() / (bs.make_base("Uploaded") + ext)
    with open(dest, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    return dest


# ------------------------------------------------------------ create backup
@superuser_json
@require_http_methods(["GET", "POST"])  # the current page calls these with GET
def create_fast_backup_with_progress(request=None, background=False, upload_to_cloud_flag=True):
    try:
        _audit(request, "create_backup")
        m = bs.create_backup(upload=upload_to_cloud_flag, trigger=f"web:{request.user}")
        return JsonResponse({
            "success": True, "file": m["file"], "size_mb": m["size_mb"],
            "timestamp": m["timestamp"], "cloud_uploaded": m["cloud"],
            "message": m["message"],
        })
    except bs.BackupError as e:
        return JsonResponse({"success": False, "message": f"Backup failed: {e}"})


@superuser_json
@require_http_methods(["GET", "POST"])
def backup_in_background(request):
    if os.path.exists(bs.backup_dir() / ".backup.lock"):
        return JsonResponse({"success": False, "message": "A backup is already running."})
    _audit(request, "create_backup_background")
    user = str(request.user)

    def _job():
        try:
            bs.create_backup(trigger=f"web-bg:{user}")
        except Exception as e:  # already logged + progress=failed inside service
            logger.error("Background backup error: %s", e)

    bs.update_progress(0, "Starting backup...", status="starting")
    threading.Thread(target=_job, daemon=True).start()
    return JsonResponse({
        "success": True, "message": "Backup started in background!",
        "progress_url": "/backup/progress/", "cloud_enabled": bs.cloud_enabled(),
    })


# --------------------------------------------------------------- read APIs
@superuser_json
def get_backup_progress(request):
    return JsonResponse({"success": True, "progress": bs.read_progress()})


@superuser_json
def get_backup_files_api(request):
    files = bs.list_backups()
    return JsonResponse({
        "success": True, "files": files, "total": len(files),
        "total_size_mb": round(sum(f["size"] for f in files) / 1048576, 2),
    })


@superuser_json
def get_backup_stats(request):
    files = bs.list_backups()
    return JsonResponse({
        "success": True, "total_files": len(files),
        "total_size_mb": round(sum(f["size"] for f in files) / 1048576, 2),
        "backup_dir": str(bs.backup_dir()),
        "latest_backup": files[0]["name"] if files else None,
        "current_progress": bs.read_progress(),
        "cloud_enabled": bs.cloud_enabled(),
        "remote_name": getattr(settings, "RCLONE_REMOTE_NAME", "gdrive"),
        "health": bs.health(),
    })


@superuser_json
def get_cloud_files(request):
    if not bs.cloud_enabled():
        return JsonResponse({"success": False, "message": "Cloud backup is disabled in settings!"})
    try:
        return JsonResponse({"success": True, "files": bs.cloud_list()})
    except Exception as e:
        return JsonResponse({"success": False, "files": [], "message": str(e)})


def get_drive_account(remote_name):
    """Google Drive account (email / name).

    In this rclone version `rclone config userinfo` does not work on Drive, so:
      1. `rclone about` is run so that rclone refreshes the token,
      2. the access token is taken from the config,
      3. the email/name is asked from the Google Drive API (about?fields=user).
    The token stays only in memory, it is not saved or logged anywhere.
    Fallback: if GDRIVE_ACCOUNT_EMAIL is set in settings.py, that is shown.
    A successful result is cached for 10 minutes.
    """
    key = "drive_account_" + str(remote_name)
    cached = cache.get(key)
    if cached is not None:
        return cached

    result = {"account_email": "", "account_name": ""}
    try:
        subprocess.run(["rclone", "about", f"{remote_name}:", "--json"],
                       capture_output=True, text=True, timeout=30)
        dump = subprocess.run(["rclone", "config", "dump"],
                              capture_output=True, text=True, timeout=15)
        cfg = json.loads(dump.stdout or "{}")
        token = json.loads((cfg.get(remote_name) or {}).get("token") or "{}")
        access = token.get("access_token")
        if access:
            req = urllib.request.Request(
                "https://www.googleapis.com/drive/v3/about?fields=user",
                headers={"Authorization": "Bearer " + access},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                user = json.loads(resp.read().decode("utf-8")).get("user") or {}
            result["account_email"] = user.get("emailAddress", "")
            result["account_name"] = user.get("displayName", "")
    except Exception as e:
        logger.warning("Drive account lookup failed: %s", e)

    if not result["account_email"]:
        result["account_email"] = getattr(settings, "GDRIVE_ACCOUNT_EMAIL", "")

    if result["account_email"]:
        cache.set(key, result, 600)
    return result


@superuser_json
def check_rclone_status(request):
    try:
        st = bs.rclone_status()
        st["success"] = st["rclone_installed"] and st["remote_configured"]
        if st["success"]:
            st.update(get_drive_account(st.get("remote_name") or
                                        getattr(settings, "RCLONE_REMOTE_NAME", "gdrive")))
        return JsonResponse(st)
    except Exception as e:
        return JsonResponse({"success": False, "rclone_installed": False,
                             "remote_configured": False, "message": str(e)})


# --------------------------------------------------------- file operations
@superuser_json
def download_backup(request, filename):
    try:
        path = bs.resolve_local(unquote(filename))
    except bs.BackupError:
        raise Http404("File not found!")
    _audit(request, f"download {path.name}")
    _hist(request, "download", path.name)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@superuser_json
@require_POST
def delete_backup_file(request, filename):
    filename = unquote(filename)
    if request.POST.get("file_type") == "cloud":
        return JsonResponse({"success": False,
                             "message": "Cloud files are removed automatically by retention."})
    try:
        path = bs.resolve_local(filename)
        _audit(request, f"delete {path.name}")
        base = bs._base(path.name)
        for p in bs.backup_dir().iterdir():
            if p.is_file() and p.name.startswith(base + "."):
                p.unlink(missing_ok=True)
        _hist(request, "delete", path.name)
        return JsonResponse({"success": True, "message": f'🗑️ "{filename}" deleted!'})
    except bs.BackupError as e:
        _hist(request, "delete", filename, "failed", str(e))
        return JsonResponse({"success": False, "message": str(e)})


def _restore_response(request, path, name, source):
    try:
        safety = bs.restore_backup(path)
        _hist(request, "restore", name, detail=f"{source} | safety copy: {safety}")
        return JsonResponse({"success": True, "restored_from": name, "safety_backup": safety,
                             "message": f'✅ Database restored from "{name}". '
                                        "Previous database kept as safety copy."})
    except bs.BackupError as e:
        _hist(request, "restore", name, "failed", str(e))
        return JsonResponse({"success": False, "message": f"Restore failed: {e}"})


@superuser_json
@require_POST
def restore_local_backup(request, filename):
    try:
        path = bs.resolve_local(unquote(filename))
    except bs.BackupError as e:
        return JsonResponse({"success": False, "message": str(e)})
    _audit(request, f"restore_local {path.name}")
    return _restore_response(request, path, path.name, "local")


@superuser_json
@require_POST
def restore_from_cloud(request, filename):
    filename = unquote(filename)
    if not bs.cloud_enabled():
        return JsonResponse({"success": False, "message": "Cloud backup is disabled!"})
    if not any(f["name"] == filename for f in _safe_cloud_list()):
        return JsonResponse({"success": False, "message": "File not found on cloud."})
    try:
        _audit(request, f"restore_cloud {filename}")
        path = bs.cloud_download(filename, bs.backup_dir())
        return _restore_response(request, path, filename, "Google Drive")
    except bs.BackupError as e:
        return JsonResponse({"success": False, "message": str(e)})


def _safe_cloud_list():
    try:
        return bs.cloud_list()
    except Exception:
        return []


@superuser_json
@require_POST
def upload_all_backups(request):
    if not bs.cloud_enabled():
        return JsonResponse({"success": False, "message": "Cloud backup is disabled!"})
    files = bs.list_backups()
    ok, results = 0, []
    for f in files:
        try:
            bs.cloud_upload(f["path"])
            ok += 1
            results.append({"success": True, "file_name": f["name"]})
        except Exception as e:
            results.append({"success": False, "file_name": f["name"], "message": str(e)})
    _hist(request, "drive_upload", status="ok" if ok == len(files) else "warning",
          detail=f"{ok}/{len(files)} files uploaded")
    return JsonResponse({"success": True, "message": f"✅ {ok}/{len(files)} files uploaded!",
                         "results": results, "total": len(results)})


@superuser_json
@require_POST
def upload_single_backup(request, filename):
    if not bs.cloud_enabled():
        return JsonResponse({"success": False, "message": "Cloud backup is disabled!"})
    try:
        path = bs.resolve_local(unquote(filename))
        bs.cloud_upload(path)
        _hist(request, "drive_upload", path.name)
        return JsonResponse({"success": True, "message": f"✅ Uploaded: {path.name}"})
    except Exception as e:
        _hist(request, "drive_upload", unquote(filename), "failed", str(e))
        return JsonResponse({"success": False, "message": str(e)})


@superuser_page
def upload_backup_file(request):
    if request.method == "POST" and request.FILES.get("backup_file"):
        try:
            path = _save_upload(request.FILES["backup_file"])
            _audit(request, f"upload {path.name}")
            _hist(request, "upload_file", path.name, detail=bs.human_size(path.stat().st_size))
            messages.success(request, f'✅ "{path.name}" uploaded ({bs.human_size(path.stat().st_size)}).')
        except bs.BackupError as e:
            messages.error(request, f"❌ {e}")
        return redirect("database_backup")
    return render(request, "database_backup_upload.html", {
        "company_name": CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else "ERP System",
        "allowed_extensions": list(ALLOWED_UPLOAD_EXT),
        "max_size_mb": MAX_UPLOAD_MB,
    })
