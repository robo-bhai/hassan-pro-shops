"""Frontend views: backup."""
from ..models import *
import json
import shutil
import gzip
import threading
import glob
import os
import time
import subprocess
import re
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from datetime import datetime
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from urllib.parse import unquote
from django.conf import settings
from ..models import CompanyInfo
import logging

logger = logging.getLogger('app.backup')


# --- Encrypted backup helpers -------------------------------------------------
# These three functions live in your own `db_backup_manager` module (it was not
# part of the uploaded files). Put db_backup_manager.py in the project root (next
# to manage.py) or inside the app folder; the import below finds it in either place.
try:
    from db_backup_manager import export_backup, execute_restore_from_bytes, get_latest_enc_file
except ImportError:
    try:
        from ..db_backup_manager import export_backup, execute_restore_from_bytes, get_latest_enc_file
    except ImportError:
        def _backup_manager_missing(*args, **kwargs):
            raise RuntimeError(
                "db_backup_manager.py not found. Add it next to manage.py "
                "(it must provide export_backup, execute_restore_from_bytes, get_latest_enc_file)."
            )

        export_backup = execute_restore_from_bytes = _backup_manager_missing

        def get_latest_enc_file():
            return None
# ------------------------------------------------------------------------------


# ============================================
# DATABASE BACKUP VIEW (Simple)
# ============================================
@login_required
def database_backup_simple(request):
    """Simple database backup without custom admin"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can access backup.')
        return redirect('dashboard')
    
    import subprocess
    import os
    from datetime import datetime
    import json
    
    # Backup directory - Termux ke liye
    backup_dir = '/storage/emulated/0/Download/Backups/'
    
    # Agar folder exist nahi karta to create karo
    try:
        os.makedirs(backup_dir, exist_ok=True)
    except Exception as e:
        messages.warning(request, f'Cannot create backup directory: {e}')
        backup_dir = '/storage/emulated/0/'
    
    # ========== CREATE BACKUP ==========
    if request.method == 'POST':
        action = request.POST.get('action', '')
        
        # JSON Backup (dumpdata)
        if action == 'json_backup':
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.json')
            
            try:
                result = subprocess.run(
                    ['python', 'manage.py', 'dumpdata', '--indent', '2', 
                     '--exclude', 'contenttypes', '--exclude', 'auth.permission',
                     '--output', backup_file],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    messages.success(request, f'✅ JSON Backup created: {backup_file}')
                else:
                    messages.error(request, f'❌ Error: {result.stderr}')
            except Exception as e:
                messages.error(request, f'❌ Error: {str(e)}')
        
        # SQLite Backup (copy database file)
        elif action == 'sqlite_backup':
            import shutil
            from django.conf import settings
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            db_path = settings.DATABASES['default']['NAME']
            
            if os.path.exists(db_path) and 'sqlite' in settings.DATABASES['default']['ENGINE']:
                backup_file = os.path.join(backup_dir, f'db_sqlite_{timestamp}.sqlite')
                try:
                    shutil.copy2(db_path, backup_file)
                    messages.success(request, f'✅ SQLite Database copied to: {backup_file}')
                except Exception as e:
                    messages.error(request, f'❌ Error copying database: {e}')
            else:
                messages.error(request, '❌ Not a SQLite database or database file not found!')
        
        return redirect('database_backup_simple')
    
    # ========== DELETE BACKUP ==========
    if request.GET.get('delete'):
        filename = request.GET.get('delete')
        if '..' not in filename and '/' not in filename:
            file_path = os.path.join(backup_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    messages.success(request, f'🗑️ Deleted: {filename}')
                except Exception as e:
                    messages.error(request, f'❌ Error deleting: {e}')
            else:
                messages.error(request, 'File not found!')
        return redirect('database_backup_simple')
    
    # ========== RESTORE BACKUP ==========
    if request.GET.get('restore'):
        filename = request.GET.get('restore')
        if '..' not in filename and '/' not in filename:
            file_path = os.path.join(backup_dir, filename)
            if os.path.exists(file_path):
                try:
                    if filename.endswith('.json'):
                        result = subprocess.run(
                            ['python', 'manage.py', 'loaddata', file_path],
                            capture_output=True, text=True
                        )
                        if result.returncode == 0:
                            messages.success(request, f'✅ Database restored from: {filename}')
                        else:
                            messages.error(request, f'❌ Restore error: {result.stderr}')
                    elif filename.endswith('.sqlite'):
                        import shutil
                        from django.conf import settings
                        db_path = settings.DATABASES['default']['NAME']
                        # Pehle old database backup bana lo
                        safety_backup = db_path + '.before_restore'
                        shutil.copy2(db_path, safety_backup)
                        shutil.copy2(file_path, db_path)
                        messages.success(request, f'✅ SQLite restored! Old DB saved as {safety_backup}')
                    else:
                        messages.error(request, 'Unsupported file format!')
                except Exception as e:
                    messages.error(request, f'❌ Error: {e}')
            else:
                messages.error(request, 'File not found!')
        return redirect('database_backup_simple')
    
    # ========== LIST BACKUP FILES ==========
    backup_files = []
    file_sizes = {}
    file_dates = {}
    
    if os.path.exists(backup_dir):
        files = os.listdir(backup_dir)
        files = [f for f in files if f.endswith(('.json', '.sqlite'))]
        files.sort(reverse=True)
        
        for f in files:
            file_path = os.path.join(backup_dir, f)
            size = os.path.getsize(file_path)
            mtime = os.path.getmtime(file_path)
            
            # Size formatting
            if size < 1024:
                file_sizes[f] = f"{size} B"
            elif size < 1024 * 1024:
                file_sizes[f] = f"{size / 1024:.1f} KB"
            else:
                file_sizes[f] = f"{size / (1024 * 1024):.1f} MB"
            
            # Date formatting
            file_dates[f] = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            backup_files.append(f)
    
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'backup_files': backup_files,
        'file_sizes': file_sizes,
        'file_dates': file_dates,
        'backup_dir': backup_dir,
    }
    return render(request, 'database_backup.html', context)


@login_required
def database_backup_view(request):
    """
    Handles encrypted backup generation (HTTP download) and 
    schema-validated transactional database restoration using Python modules.
    """
    restore_latest = request.GET.get("restore_latest")

    # ---- 1. RESTORE LOGIC (VIA DISK / LATEST FILE) ----
    if restore_latest:
        latest_file = get_latest_enc_file()
        if latest_file and os.path.exists(latest_file):
            try:
                with open(latest_file, "rb") as f:
                    file_bytes = f.read()
                
                success, msg = execute_restore_from_bytes(file_bytes)
                if success:
                    messages.success(request, f"🎉 Database successfully restored! ({msg})")
                else:
                    messages.error(request, f"❌ Restore Failed: {msg}")
            except Exception as e:
                messages.error(request, f"❌ File read error: {e}")
        else:
            messages.error(request, "❌ No local `.enc` backup file found to restore.")
        return redirect("database_backup")

    # ---- 2. CREATE BACKUP & DOWNLOAD LOGIC (POST) ----
    if request.method == "POST":
        action = request.POST.get("action")

        # Handles Direct Encrypted File Generation & HTTP Download
        if action in ["encrypted_backup", "json_backup", "sqlite_backup"]:
            try:
                # Generates encrypted bytes dynamically via db_backup_manager
                encrypted_bytes = export_backup()
                
                db_name = os.environ.get('DB_NAME', 'db')
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"backup_{db_name}_{timestamp}.enc"

                # Direct stream response triggering browser download
                response = HttpResponse(encrypted_bytes, content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            except Exception as e:
                messages.error(request, f"❌ Backup Generation Failed: {e}")
                return redirect("database_backup")

        # Handles UI File Upload Restoration
        elif action == "restore_upload" and request.FILES.get("backup_file"):
            uploaded_file = request.FILES["backup_file"]
            file_bytes = uploaded_file.read()

            success, msg = execute_restore_from_bytes(file_bytes)
            if success:
                messages.success(request, f"🎉 Uploaded backup restored successfully!")
            else:
                messages.error(request, f"❌ Restore Failed: {msg}")
            return redirect("database_backup")

    # ---- 3. RENDER DATA PROCESSING ----
    # Inspect local directory for existing .enc files
    latest_enc = get_latest_enc_file()
    backup_files = []
    file_sizes = {}
    file_dates = {}

    if latest_enc and os.path.exists(latest_enc):
        filename = os.path.basename(latest_enc)
        stat = os.stat(latest_enc)
        
        backup_files.append(filename)
        file_sizes[filename] = f"{round(stat.st_size / 1024, 2)} KB"
        file_dates[filename] = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    context = {
        "backup_dir": "Encrypted Database Storage (MySQL)",
        "backup_files": backup_files,
        "file_sizes": file_sizes,
        "file_dates": file_dates,
        "db_name": os.environ.get('DB_NAME', 'MySQL Database'),
    }
    return render(request, "database_backup.html", context)


def upload_to_cloud(file_path, remote_name='gdrive', remote_dir='TermuxBackups'):
    """
    Upload backup file to Google Drive using rclone
    Returns: dict with success, message, file_name
    """
    try:
        # Check if rclone is installed
        check_rclone = subprocess.run(['which', 'rclone'], capture_output=True, text=True)
        if check_rclone.returncode != 0:
            return {
                'success': False, 
                'message': '⚠️ Rclone not installed! Install: pkg install rclone'
            }
        
        # Check if remote exists
        check_remote = subprocess.run(
            ['rclone', 'ls', f'{remote_name}:'],
            capture_output=True, text=True
        )
        if check_remote.returncode != 0:
            return {
                'success': False, 
                'message': f'❌ Remote "{remote_name}" not found! Run: rclone config'
            }
        
        filename = os.path.basename(file_path)
        remote_path = f"{remote_name}:{remote_dir}/{filename}"
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        logger.info(f"☁️ Uploading to Google Drive: {filename} ({file_size_mb:.1f} MB)")
        
        # Upload command with progress
        cmd = [
            "rclone", "copy",
            file_path,
            remote_path,
            "--progress",
            "--stats", "1s",
            "--transfers", "2"
        ]
        
        # Run upload
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ Uploaded to Google Drive: {filename}")
            return {
                'success': True, 
                'message': f'✅ Uploaded: {filename}',
                'file_name': filename,
                'size_mb': round(file_size_mb, 2)
            }
        else:
            error_msg = result.stderr or "Unknown error"
            logger.error(f"❌ Upload failed: {error_msg}")
            return {
                'success': False, 
                'message': f'❌ Upload failed: {error_msg[:100]}'
            }
            
    except Exception as e:
        logger.error(f"❌ Upload error: {str(e)}")
        return {'success': False, 'message': f'❌ Error: {str(e)}'}


def upload_to_cloud_progress(file_path, step_callback=None, remote_name='gdrive', remote_dir='TermuxBackups'):
    """
    Upload backup file to Google Drive with progress tracking
    """
    try:
        filename = os.path.basename(file_path)
        remote_path = f"{remote_name}:{remote_dir}/{filename}"
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if step_callback:
            step_callback(3.2, f'☁️ Uploading to Drive... 0%')
        
        # Use rclone with progress
        cmd = [
            "rclone", "copy",
            file_path,
            remote_path,
            "--progress",
            "--stats", "1s",
            "--transfers", "2"
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Read output for progress
        last_percent = 0
        for line in process.stdout:
            # Parse progress from rclone output
            if '%' in line and 'Transferred:' in line:
                try:
                    # Extract percentage
                    parts = line.split()
                    for part in parts:
                        if '%' in part and part.replace('%', '').replace('.', '').isdigit():
                            percent = float(part.replace('%', ''))
                            if percent > last_percent:
                                last_percent = percent
                                if step_callback:
                                    step_callback(
                                        3.2 + (percent / 100) * 0.8,
                                        f'☁️ Uploading to Drive... {percent:.0f}%'
                                    )
                                break
                except:
                    pass
        
        process.wait()
        
        if process.returncode == 0:
            if step_callback:
                step_callback(4.0, f'☁️ Upload complete! {file_size_mb:.1f} MB')
            
            logger.info(f"✅ Uploaded to Google Drive: {filename}")
            return {
                'success': True, 
                'message': f'✅ Uploaded: {filename} ({file_size_mb:.1f} MB)',
                'file_name': filename,
                'size_mb': round(file_size_mb, 2)
            }
        else:
            return {'success': False, 'message': '❌ Upload failed'}
            
    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        return {'success': False, 'message': f'❌ Error: {str(e)}'}


def upload_all_backups(request):
    """Manual: Upload all local backups to Google Drive"""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Access denied!'})
    
    backup_dir = settings.BACKUP_DIR
    files = glob.glob(os.path.join(backup_dir, '*.sqlite3.gz'))
    
    if not files:
        return JsonResponse({'success': False, 'message': 'No backup files found!'})
    
    results = []
    success_count = 0
    
    for file in files:
        result = upload_to_cloud(file)
        results.append(result)
        if result['success']:
            success_count += 1
    
    return JsonResponse({
        'success': True,
        'message': f'✅ {success_count}/{len(files)} files uploaded!',
        'results': results,
        'total': len(results),
    })


def update_backup_progress(step, total, current, message, status='in_progress'):
    """Update backup progress in JSON file"""
    steps = {
        1: '📁 Copying Database',
        2: '🗜️ Compressing Backup (GZIP)',
        3: '☁️ Uploading to Cloud',
        4: '🧹 Cleaning Old Backups',
        5: '✅ Backup Complete',
    }
    
    progress_data = {
        'step': step,
        'total': total,
        'current': current,
        'percentage': round((current / total) * 100, 1) if total > 0 else 0,
        'message': message,
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'step_name': steps.get(step, f'Step {step}'),
    }
    
    try:
        with open(settings.BACKUP_PROGRESS_FILE, 'w') as f:
            json.dump(progress_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to update progress: {e}")


def get_backup_progress(request):
    """API: Get current backup progress"""
    try:
        if os.path.exists(settings.BACKUP_PROGRESS_FILE):
            with open(settings.BACKUP_PROGRESS_FILE, 'r') as f:
                progress = json.load(f)
            return JsonResponse({'success': True, 'progress': progress})
        else:
            return JsonResponse({
                'success': True,
                'progress': {
                    'step': 0,
                    'percentage': 0,
                    'message': 'No backup in progress',
                    'status': 'idle'
                }
            })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


def create_fast_backup_with_progress(request=None, background=False, upload_to_cloud_flag=True):
    """Fast backup with real-time progress tracking + Cloud upload"""
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        db_path = settings.BASE_DIR / 'db.sqlite3'
        backup_dir = settings.BACKUP_DIR
        os.makedirs(backup_dir, exist_ok=True)
        
        # ==========================================
        # STEP 1: Copy Database (20%)
        # ==========================================
        update_backup_progress(
            step=1,
            total=6,  # 6 steps including cloud
            current=1,
            message='📁 Copying database file...',
            status='in_progress'
        )
        
        temp_file = os.path.join(backup_dir, f'backup_{timestamp}.sqlite3')
        shutil.copy2(db_path, temp_file)
        
        # ==========================================
        # STEP 2: Compress Backup (40%)
        # ==========================================
        update_backup_progress(
            step=2,
            total=6,
            current=2,
            message='🗜️ Compressing backup (GZIP)...',
            status='in_progress'
        )
        
        gzip_file = os.path.join(backup_dir, f'backup_{timestamp}.sqlite3.gz')
        
        with open(temp_file, 'rb') as f_in:
            with gzip.open(gzip_file, 'wb', compresslevel=1) as f_out:
                compressed = 0
                chunk_size = 1024 * 1024
                temp_size = os.path.getsize(temp_file)
                while True:
                    chunk = f_in.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    compressed += len(chunk)
                    if temp_size > 0:
                        percent = (compressed / temp_size) * 100
                        sub_progress = 2 + (percent / 100) * 1.5
                        update_backup_progress(
                            step=2,
                            total=6,
                            current=min(sub_progress, 3.5),
                            message=f'🗜️ Compressing... {percent:.0f}%',
                            status='in_progress'
                        )
        
        os.remove(temp_file)
        
        # ==========================================
        # STEP 3: Upload to Cloud (20%)
        # ==========================================
        cloud_success = False
        cloud_message = '☁️ Cloud upload skipped (disabled)'
        
        if upload_to_cloud_flag and settings.RCLONE_ENABLED:
            update_backup_progress(
                step=3,
                total=6,
                current=3.2,
                message='☁️ Uploading to Google Drive... Starting...',
                status='in_progress'
            )
            
            def update_cloud_progress(step_val, msg):
                update_backup_progress(
                    step=3,
                    total=6,
                    current=step_val,
                    message=msg,
                    status='in_progress'
                )
            
            result = upload_to_cloud_progress(
                gzip_file,
                step_callback=update_cloud_progress
            )
            
            if result['success']:
                cloud_success = True
                cloud_message = f'☁️ {result["message"]}'
                update_backup_progress(
                    step=3,
                    total=6,
                    current=4,
                    message=cloud_message,
                    status='in_progress'
                )
            else:
                cloud_message = f'⚠️ {result["message"]}'
                update_backup_progress(
                    step=3,
                    total=6,
                    current=3.8,
                    message=cloud_message,
                    status='in_progress'
                )
        else:
            # Cloud upload disabled
            cloud_message = '☁️ Cloud upload disabled in settings'
            update_backup_progress(
                step=3,
                total=6,
                current=4,
                message=cloud_message,
                status='in_progress'
            )
        
        # ==========================================
        # STEP 4: Clean Old Backups (10%)
        # ==========================================
        update_backup_progress(
            step=4,
            total=6,
            current=4.5,
            message='🧹 Cleaning old backups...',
            status='in_progress'
        )
        
        clean_old_backups(keep=5)
        
        # ==========================================
        # STEP 5: Complete (10%)
        # ==========================================
        size_mb = os.path.getsize(gzip_file) / (1024 * 1024)
        
        final_message = f'✅ Backup complete! Size: {size_mb:.1f} MB'
        if cloud_success:
            final_message += f' | ☁️ Uploaded to Drive!'
        elif settings.RCLONE_ENABLED and not cloud_success:
            final_message += f' | ⚠️ Cloud upload failed'
        
        update_backup_progress(
            step=5,
            total=6,
            current=6,
            message=final_message,
            status='completed'
        )
        
        logger.info(f"Backup created: {gzip_file} ({size_mb:.1f} MB) | Cloud: {cloud_success}")
        
        if request:
            return JsonResponse({
                'success': True,
                'file': gzip_file,
                'size_mb': round(size_mb, 2),
                'timestamp': timestamp,
                'cloud_uploaded': cloud_success,
                'message': final_message,
            })
        
        return gzip_file
        
    except Exception as e:
        error_msg = f"Backup failed: {str(e)}"
        logger.error(error_msg)
        update_backup_progress(
            step=0,
            total=6,
            current=0,
            message=f'❌ {error_msg}',
            status='failed'
        )
        if request:
            return JsonResponse({'success': False, 'message': error_msg})
        raise


def backup_in_background(request):
    """Background backup with progress tracking + Cloud upload"""
    
    # Check if cloud upload is enabled
    upload_to_cloud_flag = getattr(settings, 'RCLONE_ENABLED', False)
    
    def _backup():
        try:
            update_backup_progress(
                step=0,
                total=6,
                current=0,
                message='🔄 Starting backup...',
                status='starting'
            )
            time.sleep(0.5)
            create_fast_backup_with_progress(
                background=True,
                upload_to_cloud_flag=upload_to_cloud_flag
            )
        except Exception as e:
            logger.error(f"Background backup error: {e}")
            update_backup_progress(
                step=0,
                total=6,
                current=0,
                message=f'❌ Error: {str(e)}',
                status='failed'
            )
    
    thread = threading.Thread(target=_backup)
    thread.daemon = True
    thread.start()
    
    cloud_status = 'Enabled' if upload_to_cloud_flag else 'Disabled'
    
    return JsonResponse({
        'success': True,
        'message': f'✅ Backup started in background! Cloud: {cloud_status}',
        'progress_url': '/backup/progress/',
        'cloud_enabled': upload_to_cloud_flag,
    })


def clean_old_backups(keep=5):
    """Sirf last 'keep' backups rakho"""
    backup_dir = settings.BACKUP_DIR
    files = sorted(
        glob.glob(os.path.join(backup_dir, '*.sqlite3.gz')) + 
        glob.glob(os.path.join(backup_dir, '*.sqlite3')),
        key=os.path.getctime
    )
    
    deleted = []
    for file in files[:-keep]:
        try:
            os.remove(file)
            deleted.append(file)
        except Exception:
            pass
    
    return deleted


def get_backup_files_api(request):
    """AJAX: Get backup files list"""
    files = []
    backup_dir = settings.BACKUP_DIR
    total_size = 0
    
    for file in glob.glob(os.path.join(backup_dir, '*.sqlite3*')):
        stat = os.stat(file)
        size_mb = stat.st_size / (1024 * 1024)
        total_size += stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime)
        
        files.append({
            'name': os.path.basename(file),
            'size_mb': round(size_mb, 2),
            'size_display': f"{size_mb:.1f} MB",
            'modified': mtime.strftime('%Y-%m-%d %H:%M:%S'),
            'is_compressed': file.endswith('.gz'),
            'path': file,
        })
    
    files.sort(key=lambda x: x['modified'], reverse=True)
    
    return JsonResponse({
        'success': True,
        'files': files,
        'total': len(files),
        'total_size_mb': round(total_size / (1024 * 1024), 2),
    })


def _perform_restore(file_path, filename):
    """
    ✅ Complete restore helper function
    Restore database from backup file
    """
    import shutil
    import gzip
    import os
    from django.conf import settings
    from datetime import datetime
    
    try:
        db_path = settings.BASE_DIR / 'db.sqlite3'
        
        # ========================================== #
        # STEP 1: Decompress if needed
        # ========================================== #
        restore_file = file_path
        
        if filename.endswith('.gz'):
            decompressed_file = file_path.replace('.gz', '')
            try:
                with gzip.open(file_path, 'rb') as f_in:
                    with open(decompressed_file, 'wb') as f_out:
                        f_out.write(f_in.read())
                restore_file = decompressed_file
                logger.info(f"Decompressed: {restore_file}")
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to decompress: {str(e)}'
                })
        
        # ========================================== #
        # STEP 2: Safety backup of current DB
        # ========================================== #
        safety_backup = settings.BASE_DIR / f'db_safety_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sqlite3'
        try:
            shutil.copy2(db_path, safety_backup)
            logger.info(f"Safety backup created: {safety_backup}")
        except Exception as e:
            logger.warning(f"Could not create safety backup: {e}")
        
        # ========================================== #
        # STEP 3: Restore database
        # ========================================== #
        shutil.copy2(restore_file, db_path)
        logger.info(f"Database restored from: {restore_file}")
        
        # ========================================== #
        # STEP 4: Clean temp files
        # ========================================== #
        if restore_file != file_path and os.path.exists(restore_file):
            try:
                os.remove(restore_file)
            except:
                pass
        
        # ========================================== #
        # STEP 5: Return success
        # ========================================== #
        return JsonResponse({
            'success': True,
            'message': f'✅ Database restored successfully from "{filename}"!',
            'safety_backup': str(safety_backup),
            'restored_from': filename,
        })
        
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Restore failed: {str(e)}'
        })


def get_backup_stats(request):
    """Get backup statistics"""
    backup_dir = settings.BACKUP_DIR
    files = glob.glob(os.path.join(backup_dir, '*.sqlite3*'))
    
    total_size = 0
    for f in files:
        total_size += os.path.getsize(f)
    
    progress = None
    if os.path.exists(settings.BACKUP_PROGRESS_FILE):
        try:
            with open(settings.BACKUP_PROGRESS_FILE, 'r') as f:
                progress = json.load(f)
        except:
            pass
    
    return JsonResponse({
        'success': True,
        'total_files': len(files),
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'backup_dir': backup_dir,
        'latest_backup': os.path.basename(files[0]) if files else None,
        'current_progress': progress,
        'cloud_enabled': getattr(settings, 'RCLONE_ENABLED', False),
        'remote_name': getattr(settings, 'RCLONE_REMOTE_NAME', 'gdrive'),
    })


@login_required
def delete_backup_file(request, filename):
    """Delete a backup file - FIXED"""
    
    # ✅ Superuser OR Staff allow karo
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied! Only administrators can delete backups.'})
    
    filename = unquote(filename)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'})
    
    import re
    if not re.match(r'^[\w\-\.]+$', filename):
        return JsonResponse({'success': False, 'message': 'Invalid filename'})
    
    file_type = request.POST.get('file_type', 'local')
    
    if file_type == 'cloud':
        try:
            if not getattr(settings, 'RCLONE_ENABLED', False):
                return JsonResponse({'success': False, 'message': 'Cloud not enabled!'})
            
            remote_name = getattr(settings, 'RCLONE_REMOTE_NAME', 'gdrive')
            remote_dir = getattr(settings, 'RCLONE_REMOTE_DIR', 'TermuxBackups')
            remote_path = f"{remote_name}:{remote_dir}/{filename}"
            
            cmd = ["rclone", "deletefile", remote_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return JsonResponse({'success': True, 'message': f'🗑️ "{filename}" deleted from cloud!'})
            else:
                return JsonResponse({'success': False, 'message': f'Delete failed: {result.stderr}'})
                
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    else:
        backup_dir = getattr(settings, 'BACKUP_DIR', '/storage/emulated/0/Download/Backups')
        file_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(file_path):
            return JsonResponse({'success': False, 'message': 'File not found!'})
        
        try:
            os.remove(file_path)
            return JsonResponse({'success': True, 'message': f'🗑️ "{filename}" deleted!'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})


@login_required
def download_backup(request, filename):
    """Download a backup file - COMPLETE FIX"""
    
    # ✅ Superuser OR Staff allow karo
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied! Only administrators can download backups.'})
    
    # ✅ Decode filename
    filename = unquote(filename)
    
    # ✅ Validate filename (security)
    import re
    if not re.match(r'^[\w\-\.]+$', filename):
        raise Http404("Invalid filename")
    
    backup_dir = getattr(settings, 'BACKUP_DIR', '/storage/emulated/0/Download/Backups')
    file_path = os.path.join(backup_dir, filename)
    
    if not os.path.exists(file_path):
        raise Http404("File not found!")
    
    response = FileResponse(open(file_path, 'rb'))
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def check_rclone_status(request):
    """Check rclone and Google Drive status"""
    try:
        # Check rclone installed
        check_rclone = subprocess.run(['which', 'rclone'], capture_output=True, text=True)
        rclone_installed = check_rclone.returncode == 0
        
        if not rclone_installed:
            return JsonResponse({
                'success': False,
                'rclone_installed': False,
                'message': '⚠️ Rclone not installed! Install: pkg install rclone',
                'remote_configured': False
            })
        
        # Check remote configured
        check_remote = subprocess.run(
            ['rclone', 'ls', 'gdrive:'],
            capture_output=True, text=True,
            timeout=10
        )
        remote_configured = check_remote.returncode == 0
        
        return JsonResponse({
            'success': True,
            'rclone_installed': True,
            'remote_configured': remote_configured,
            'remote_name': 'gdrive',
            'remote_dir': 'TermuxBackups',
            'message': '✅ Google Drive ready!' if remote_configured else '⚠️ Remote not configured. Run: rclone config',
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}',
            'rclone_installed': False,
            'remote_configured': False
        })


@login_required
def restore_from_cloud(request, filename):
    """Restore database from Google Drive backup - FIXED"""
    
    # ✅ Superuser OR Staff allow karo
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied! Only administrators can restore from cloud.'})
    
    filename = unquote(filename)
    
    try:
        if not getattr(settings, 'RCLONE_ENABLED', False):
            return JsonResponse({
                'success': False,
                'message': 'Cloud upload is disabled in settings!'
            })
        
        import re
        if not re.match(r'^[\w\-\.]+$', filename):
            return JsonResponse({
                'success': False,
                'message': 'Invalid filename! Only letters, numbers, dots and hyphens allowed.'
            })
        
        remote_name = getattr(settings, 'RCLONE_REMOTE_NAME', 'gdrive')
        remote_dir = getattr(settings, 'RCLONE_REMOTE_DIR', 'TermuxBackups')
        remote_path = f"{remote_name}:{remote_dir}/{filename}"
        
        backup_dir = getattr(settings, 'BACKUP_DIR', '/storage/emulated/0/Download/Backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        temp_file = os.path.join(backup_dir, f"temp_restore_{filename}")
        
        cmd = ["rclone", "copyto", remote_path, temp_file]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            return JsonResponse({
                'success': False,
                'message': f'Download failed: {result.stderr}'
            })
        
        if not os.path.exists(temp_file):
            return JsonResponse({
                'success': False,
                'message': 'Downloaded file not found!'
            })
        
        return _perform_restore(temp_file, filename)
        
    except subprocess.TimeoutExpired:
        return JsonResponse({'success': False, 'message': 'Download timed out!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def restore_local_backup(request, filename):
    """Restore database from local backup - FIXED"""
    
    # ✅ Superuser OR Staff allow karo
    if not request.user.is_superuser and not request.user.is_staff:
        return JsonResponse({'success': False, 'message': 'Access denied! Only administrators can restore backups.'})
    
    filename = unquote(filename)
    
    try:
        import re
        if not re.match(r'^[\w\-\.]+$', filename):
            return JsonResponse({
                'success': False,
                'message': 'Invalid filename!'
            })
        
        backup_dir = getattr(settings, 'BACKUP_DIR', '/storage/emulated/0/Download/Backups')
        file_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(file_path):
            return JsonResponse({'success': False, 'message': 'Backup file not found!'})
        
        return _perform_restore(file_path, filename)
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


def restore_database(file_path, filename):
    """Restore database from backup file"""
    import shutil
    
    try:
        db_path = settings.BASE_DIR / 'db.sqlite3'
        
        # Check if file is compressed
        if filename.endswith('.gz'):
            import gzip
            temp_file = file_path.replace('.gz', '')
            with gzip.open(file_path, 'rb') as f_in:
                with open(temp_file, 'wb') as f_out:
                    f_out.write(f_in.read())
            file_path = temp_file
        
        # Backup current database before restore (safety)
        safety_backup = settings.BASE_DIR / f'db_backup_before_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sqlite3'
        shutil.copy2(db_path, safety_backup)
        
        # Restore
        shutil.copy2(file_path, db_path)
        
        # Clean temp file
        if file_path != os.path.join(settings.BACKUP_DIR, filename):
            try:
                os.remove(file_path)
            except:
                pass
        
        return JsonResponse({
            'success': True,
            'message': f'✅ Database restored from {filename}',
            'safety_backup': str(safety_backup)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


def get_cloud_files(request):
    """Get list of backup files from Google Drive"""
    try:
        if not settings.RCLONE_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Cloud upload is disabled in settings!'
            })
        
        cmd = ["rclone", "lsjson", f"{settings.RCLONE_REMOTE_NAME}:{settings.RCLONE_REMOTE_DIR}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return JsonResponse({'success': False, 'files': []})
        
        files_data = json.loads(result.stdout)
        files = []
        
        for f in files_data:
            if not f.get('IsDir', False):
                name = f.get('Name', '')
                if name.endswith('.sqlite3.gz') or name.endswith('.sqlite3'):
                    files.append({
                        'name': name,
                        'size': f.get('Size', 0),
                        'size_display': f"{f.get('Size', 0) / (1024*1024):.1f} MB",
                        'modified': f.get('ModTime', '')[:19].replace('T', ' ')
                    })
        
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return JsonResponse({
            'success': True,
            'files': files
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
def upload_backup_file(request):
    """
    Internal storage se backup file select karke local backup folder mein add karein
    """
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Only superuser can upload backup files.')
        return redirect('database_backup')
    
    if request.method == 'POST' and request.FILES.get('backup_file'):
        try:
            uploaded_file = request.FILES['backup_file']
            filename = uploaded_file.name
            
            allowed_extensions = ['.sqlite3', '.sqlite3.gz', '.gz', '.json']
            is_allowed = any(filename.endswith(ext) for ext in allowed_extensions)
            
            if not is_allowed:
                messages.error(request, f'❌ Invalid file type! Allowed: {", ".join(allowed_extensions)}')
                return redirect('database_backup')
            
            if uploaded_file.size > 500 * 1024 * 1024:
                messages.error(request, '❌ File too large! Maximum size: 500MB')
                return redirect('database_backup')
            
            backup_dir = settings.BACKUP_DIR
            os.makedirs(backup_dir, exist_ok=True)
            
            file_path = os.path.join(backup_dir, filename)
            if os.path.exists(file_path):
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('_%Y%m%d_%H%M%S')
                new_filename = f"{name}{timestamp}{ext}"
                file_path = os.path.join(backup_dir, new_filename)
            else:
                new_filename = filename
            
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            size_mb = uploaded_file.size / (1024 * 1024)
            
            messages.success(
                request, 
                f'✅ File "{new_filename}" uploaded successfully! Size: {size_mb:.1f} MB'
            )
            
        except Exception as e:
            messages.error(request, f'❌ Error uploading file: {str(e)}')
        
        return redirect('database_backup')
    
    # ✅ YEH ADD KARO - GET request par upload form show karein
    context = {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'allowed_extensions': ['.sqlite3', '.sqlite3.gz', '.gz', '.json'],
        'max_size_mb': 500,
    }
    return render(request, 'database_backup_upload.html', context)
