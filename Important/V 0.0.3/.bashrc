# ==========================================
# 1. ALIASES & ENVIRONMENTAL VARIABLES
# ==========================================
alias run="python manage.py runserver"
alias bck="python ~/backup_script.py"
alias rst="python ~/backup_script.py --restore"
alias h='cd'
alias go='cd ~/storage/shared'
alias x='exit'
alias c='clear'

# Load Cargo Environment if exists
[ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"

# ==========================================
# PROGRESS BAR FUNCTION
# ==========================================
show_progress() {
    local duration=$1
    local message=$2
    local width=40
    
    echo -n "$message "
    for ((i=0; i<=width; i++)); do
        local percent=$((i * 100 / width))
        printf "\r$message ["
        for ((j=0; j<i; j++)); do printf "▓"; done
        for ((j=i; j<width; j++)); do printf "░"; done
        printf "] %3d%%" "$percent"
        sleep $(echo "$duration / $width" | bc -l 2>/dev/null || echo "0.05")
    done
    echo ""
}

# ==========================================
# CHECK IF SERVER IS REALLY READY
# ==========================================
wait_for_server() {
    local url="http://127.0.0.1:8000"
    local max_attempts=20
    local attempt=1
    
    echo -n "⏳ Waiting for server to be ready"
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s --head --max-time 2 "$url" > /dev/null 2>&1; then
            echo ""
            echo "✓ Server is ready after $attempt seconds"
            return 0
        fi
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo ""
    echo "⚠️ Server may not be fully ready"
    return 1
}

# ==========================================
# OPEN CHROME FUNCTION (Termux)
# ==========================================
open_chrome() {
    local url="http://127.0.0.1:8000"
    
    echo "🌐 Opening Chrome..."
    
    if command -v am > /dev/null 2>&1; then
        am start -a android.intent.action.VIEW -d "$url" com.android.chrome/com.google.android.apps.chrome.Main > /dev/null 2>&1
        sleep 2
        input keyevent 66 > /dev/null 2>&1
        echo "✓ Chrome opened with page load"
    elif command -v termux-open-url > /dev/null 2>&1; then
        termux-open-url "$url" > /dev/null 2>&1
        echo "✓ Browser opened"
    else
        echo "⚠️ Cannot open browser automatically"
        echo "📱 Please open manually: $url"
    fi
}

# ==========================================
# ENGINE START WITH PROGRESS BAR + AUTO CHROME
# ==========================================
start_engine() {
    clear
    echo ""
    echo "   ╔══════════════════════════════════════╗"
    echo "   ║     🚀 STARTING ENGINE 🚀            ║"
    echo "   ╚══════════════════════════════════════╝"
    echo ""
    
    # Step 1: Check hidden directory
    echo -n "🔍 Checking vault access... "
    if [ -d "$HIDDEN_DIR" ]; then
        echo "✓"
    else
        echo "✗"
        echo "❌ Vault not found!"
        exit
    fi
    
    # Step 2: Navigate to project
    echo -n "📂 Navigating to project... "
    cd "$HIDDEN_DIR"
    echo "✓"
    
    # Step 3: Check manage.py
    echo -n "🔧 Validating Django project... "
    if [ -f "manage.py" ]; then
        echo "✓"
    else
        echo "✗"
        echo "❌ Invalid Django project!"
        exit
    fi
    
    echo ""
    show_progress 2 "🔧 Initializing components..."
    show_progress 1.5 "📦 Loading modules..."
    show_progress 2 "🔌 Connecting to database..."
    show_progress 1.5 "🌐 Starting web server..."
    
    # Run server in background
    python manage.py runserver > /dev/null 2>&1 &
    SERVER_PID=$!
    
    echo ""
    
    # Wait for server to be really ready
    wait_for_server
    
    echo ""
    echo "   ╔══════════════════════════════════════╗"
    echo "   ║   ✅ ENGINE ACTIVE!                  ║"
    echo "   ║   📍 http://127.0.0.1:8000          ║"
    echo "   ║   🆔 PID: $SERVER_PID                ║"
    echo "   ║   ⏱️  Started: $(date '+%H:%M:%S')    ║"
    echo "   ╚══════════════════════════════════════╝"
    echo ""
    
    # Open Chrome
    open_chrome
    
    echo ""
    echo "   🌐 Chrome should load the page automatically"
    echo "   ⚠️  Press Ctrl+C to stop the engine"
    echo ""
    
    wait $SERVER_PID
}

# ==========================================
# VAULT FUNCTIONS (Simple, No Device Check)
# ==========================================

# Lock vault (encrypt)
vault-lock() {
    echo "🔒 Locking vault..."
    if [ -d "$HOME/.apps_core" ]; then
        tar -czf - "$HOME/.apps_core" 2>/dev/null | \
        openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -out "$HOME/.apps_core.tar.enc"
        if [ $? -eq 0 ]; then
            rm -rf "$HOME/.apps_core"
            echo "✅ Vault encrypted and locked!"
            echo "📦 Encrypted file: ~/.apps_core.tar.enc"
        else
            echo "❌ Encryption failed!"
        fi
    else
        echo "⚠️ Vault already locked or not found"
    fi
}

# Unlock vault (decrypt)
vault-unlock() {
    echo "🔓 Unlocking vault..."
    echo -n "Enter password: "
    read -s password
    echo ""
    
    if [ -f "$HOME/.apps_core.tar.enc" ]; then
        if openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -d -in "$HOME/.apps_core.tar.enc" \
            -pass pass:"$password" 2>/dev/null | tar -xzf - -C "$HOME/" 2>/dev/null; then
            echo "✅ Vault unlocked!"
            echo "📂 Location: ~/.apps_core"
        else
            echo "❌ Wrong password!"
        fi
    else
        echo "❌ Encrypted vault not found!"
    fi
}

# Check vault status
vault-status() {
    if [ -d "$HOME/.apps_core" ]; then
        local size=$(du -sh ~/.apps_core 2>/dev/null | cut -f1)
        echo "🔓 VAULT STATUS: UNLOCKED"
        echo "📂 Size: $size"
        echo "📍 Location: ~/.apps_core"
    elif [ -f "$HOME/.apps_core.tar.enc" ]; then
        local size=$(du -sh ~/.apps_core.tar.enc 2>/dev/null | cut -f1)
        echo "🔒 VAULT STATUS: LOCKED"
        echo "📦 Size: $size"
        echo "📍 Location: ~/.apps_core.tar.enc"
    else
        echo "❌ VAULT STATUS: NOT FOUND"
    fi
}

# ==========================================
# SECURE BACKUP TO GOOGLE DRIVE
# ==========================================
secure_backup() {
    echo "=========================================="
    echo "   🔐 SECURE BACKUP TO GOOGLE DRIVE"
    echo "=========================================="
    
    # First encrypt the vault
    vault-lock
    
    # Upload encrypted file
    if [ -f "$HOME/.apps_core.tar.enc" ]; then
        echo "📤 Uploading encrypted backup to GDrive..."
        rclone copy "$HOME/.apps_core.tar.enc" gdrive:my_projects/backups/ -P
        echo "✅ Secure backup completed!"
    else
        echo "❌ No encrypted vault found!"
    fi
}

# ==========================================
# RESTORE FROM SECURE BACKUP
# ==========================================
secure_restore() {
    echo "=========================================="
    echo "   🔐 RESTORE FROM GOOGLE DRIVE"
    echo "=========================================="
    
    # Download from GDrive
    echo "📥 Downloading encrypted backup from GDrive..."
    rclone copy gdrive:my_projects/backups/.apps_core.tar.enc "$HOME/"
    
    if [ -f "$HOME/.apps_core.tar.enc" ]; then
        vault-unlock
        echo "✅ Restore completed!"
    else
        echo "❌ No backup found on GDrive!"
    fi
}

# ==========================================
# 2. CUSTOM ZIP BACKUP FUNCTION (cz)
# ==========================================
cz() {
    local BACKUP_DIR="$HOME/storage/shared/nom_back/zip_backup"
    mkdir -p "$BACKUP_DIR"
    local LOG_FILE="$BACKUP_DIR/backup_log.txt"
    local DIR_NAME=$(basename "$PWD")
    local COUNTER=1
    local ZIP_NAME=$(printf "%s_%03d.zip" "$DIR_NAME" "$COUNTER")

    while [ -f "$BACKUP_DIR/$ZIP_NAME" ]; do
        COUNTER=$((COUNTER + 1))
        ZIP_NAME=$(printf "%s_%03d.zip" "$DIR_NAME" "$COUNTER")
    done

    echo "Creating backup: $ZIP_NAME ..."
    zip -r "$BACKUP_DIR/$ZIP_NAME" . .* -x ".." 2>/dev/null

    if [ $? -eq 0 ]; then
        local TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
        echo "[$TIMESTAMP] Created: $ZIP_NAME | Path: $PWD" >> "$LOG_FILE"
        echo "✓ Success! Saved to: $BACKUP_DIR/$ZIP_NAME"
        echo "✓ Log updated in: $LOG_FILE"
    else
        echo "✗ Error: Zip creation failed."
    fi
}

# ==========================================
# 3. GLOBAL RESTORE ENGINE (rest)
# ==========================================
rest() {
    local LOCAL_TARGET="$HOME/storage/shared/nom_back"
    mkdir -p "$LOCAL_TARGET"

    echo "[*] Fetching root directories from Google Drive..."
    local FOLDERS=()
    while IFS= read -r line; do
        FOLDERS+=("$line")
    done < <(rclone lsf gdrive:my_projects --dirs-only)

    if [ ${#FOLDERS[@]} -eq 0 ]; then
        echo "[X] No directories found in gdrive:my_projects"
        return 1
    fi

    clear
    echo "=========================================="
    echo "       GDRIVE CORE RESTORE SYSTEM         "
    echo "=========================================="
    echo "Available Cloud Folders:"
    echo "------------------------------------------"
    
    for i in "${!FOLDERS[@]}"; do
        printf " [%d] %s\n" "$((i+1))" "${FOLDERS[$i]}"
    done
    echo " [A] RESTORE ALL FOLDERS"
    echo "------------------------------------------"
    
    echo -n "Select folder number or 'A': "
    read -r CHOICE

    if [ "$CHOICE" = "A" ] || [ "$CHOICE" = "a" ]; then
        echo "[*] Restoring ALL folders from Cloud..."
        rclone copy gdrive:my_projects "$LOCAL_TARGET" -P --stats-one-line
        echo "[+] Complete restoration successful at: $LOCAL_TARGET"
    elif [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -le "${#FOLDERS[@]}" ] && [ "$CHOICE" -gt 0 ]; then
        local SELECTED_INDEX=$((CHOICE-1))
        local TARGET_FOLDER="${FOLDERS[$SELECTED_INDEX]}"
        echo "[*] Restoring folder: $TARGET_FOLDER ..."
        rclone copy "gdrive:my_projects/$TARGET_FOLDER" "$LOCAL_TARGET/$TARGET_FOLDER" -P --stats-one-line
        echo "[+] Successfully restored to: $LOCAL_TARGET/$TARGET_FOLDER"
    else
        echo "[X] Invalid Selection. Aborting restore."
    fi
}
alias rest=rest

# ==========================================
# AUTOMATED DJANGO DEPLOYER TO PYTHONANYWHERE
# ==========================================
humer() {
    local LOG_FILE="version_history.log"
    local DEFAULT_VERSION="1.0.0"
    local NEXT_VERSION=""

    # Auto-increment Logic
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
        local LAST_LINE=$(tail -n 1 "$LOG_FILE")
        local LAST_VERSION=$(echo "$LAST_LINE" | tr -s ' ' | cut -d' ' -f3)

        if [ -z "$LAST_VERSION" ]; then
            LAST_VERSION=$(echo "$LAST_LINE" | awk '{print $NF}')
        fi
        
        if [[ "$LAST_VERSION" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
            local major=${BASH_REMATCH[1]}
            local minor=${BASH_REMATCH[2]}
            local patch=${BASH_REMATCH[3]}
            patch=$((patch + 1))
            NEXT_VERSION="${major}.${minor}.${patch}"
        else
            NEXT_VERSION="$DEFAULT_VERSION"
        fi
    else
        NEXT_VERSION="$DEFAULT_VERSION"
    fi

    echo "=========================================="
    echo "🚀 Starting Deployment for Version: $NEXT_VERSION"
    echo "=========================================="

    if [ -f "latest_app.zip" ]; then
        rm latest_app.zip
    fi

    echo "📦 Creating project zip archive..."
    zip -r latest_app.zip . -x "latest_app.zip" "db.sqlite3" "db.sqlite3.backup" "*.log" "*/__pycache__/*" "current_version.txt" ".git/*" > /dev/null

    if [ ! -f "latest_app.zip" ]; then
        echo "❌ Error: Zip file creation failed!"
        return 1
    fi

    echo "🌐 Uploading to PythonAnywhere..."
    local RESPONSE=$(curl -s -X POST https://umerhassan.pythonanywhere.com/upload \
      -F "token=MeraSecureToken123" \
      -F "version=$NEXT_VERSION" \
      -F "file=@latest_app.zip")

    if [[ "$RESPONSE" == *"success"* ]]; then
        echo "✅ Success: Server Response -> $RESPONSE"
        echo "$(date '+%Y-%m-%d %H:%M:%S') $NEXT_VERSION" >> "$LOG_FILE"
        echo "📝 Log updated in $LOG_FILE (Current: $NEXT_VERSION)"
    else
        echo "❌ Deployment Failed!"
        echo "Server Response: $RESPONSE"
    fi

    if [ -f "latest_app.zip" ]; then
        rm latest_app.zip
    fi
    echo "=========================================="
}

# ==========================================
# 4. TARUX VAULT & SYNC COMMANDS
# ==========================================
HIDDEN_DIR="$HOME/.apps_core/.engine_data"
SRC_DIR="$HOME/storage/shared/django/p1"
PARENT_SRC_DIR="$HOME/storage/shared/django"
ZIP_BACKUP_SRC="$HOME/storage/shared/nom_back/zip_backup"

# Sync Commands
reuse() {
    mkdir -p "$SRC_DIR"
    cp -r "$HIDDEN_DIR"/. "$SRC_DIR/"
    echo "[+] Files copied to shared storage."
}

refun() {
    mkdir -p "$HIDDEN_DIR"
    rm -rf "${HIDDEN_DIR:?}"/*
    cp -r "$SRC_DIR"/. "$HIDDEN_DIR/"
    chmod 700 "$HIDDEN_DIR"
    echo "[+] Hidden vault updated."
}

# ==========================================
# MAIN EXECUTION
# ==========================================

# First run initialization
if [ ! -d "$HIDDEN_DIR" ]; then
    mkdir -p "$HIDDEN_DIR"
    if [ -d "$SRC_DIR" ]; then
        cp -r "$SRC_DIR"/. "$HIDDEN_DIR/"
        chmod 700 "$HIDDEN_DIR"
    fi
fi

# Check if server already running
if pgrep -f "manage.py runserver" > /dev/null 2>&1; then
    clear
    echo "[!] Server already running in another tab. Closing this tab..."
    sleep 1
    exit
fi

# Password prompt (5 seconds window)
clear
echo -n "⚙️  "
read -t 5 -s -p "" USER_KEY
echo ""

# Mode selection
if [ "$USER_KEY" = "UKBH" ]; then
    echo "[+] SAFE MODE ACTIVATED."
    
    # Sync backups to cloud
    if [ -d "$ZIP_BACKUP_SRC" ]; then
        echo "[*] Syncing backups to Google Drive..."
        rclone copy "$ZIP_BACKUP_SRC" gdrive:my_projects -P --stats-one-line
        echo "[+] Backup sync completed."
    fi
    
    cd "$PARENT_SRC_DIR" 2>/dev/null || cd "$HOME"
else
    # Normal mode - start engine
    if [ -d "$HIDDEN_DIR" ]; then
        start_engine
    else
        echo "❌ Vault not found!"
        exit
    fi
fi