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


# --- AUTOMATED DJANGO DEPLOYER TO PYTHONANYWHERE ---
humer() {
    local LOG_FILE="version_history.log"
    local DEFAULT_VERSION="1.0.0"
    local NEXT_VERSION=""

    # 1. Solid Auto-increment Logic
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
        # Log file ki aakhri line se sirf version string nikalna (akhri field)
        local LAST_LINE=$(tail -n 1 "$LOG_FILE")
        local LAST_VERSION=$(echo "$LAST_LINE" | tr -s ' ' | cut -d' ' -f3)

        # Agar kisey wajah se date format change ho, to aakhri safety check
        if [ -z "$LAST_VERSION" ]; then
            LAST_VERSION=$(echo "$LAST_LINE" | awk '{print $NF}')
        fi
        
        # Version numbers ko split karna (Major.Minor.Patch)
        if [[ "$LAST_VERSION" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
            local major=${BASH_REMATCH[1]}
            local minor=${BASH_REMATCH[2]}
            local patch=${BASH_REMATCH[3]}
            
            # Patch ko +1 barhana (e.g., 0 -> 1)
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

    # 2. Clean old zip
    if [ -f "latest_app.zip" ]; then
        rm latest_app.zip
    fi

    # 3. Create fresh zip (Fixed: Added output file exclusion to prevent corruption)
    echo "📦 Creating project zip archive..."
    zip -r latest_app.zip . -x "latest_app.zip" "db.sqlite3" "db.sqlite3.backup" "*.log" "*/__pycache__/*" "current_version.txt" ".git/*" > /dev/null

    if [ ! -f "latest_app.zip" ]; then
        echo "❌ Error: Zip file creation failed!"
        return 1
    fi

    # 4. Upload to PythonAnywhere
    echo "🌐 Uploading to PythonAnywhere..."
    local RESPONSE=$(curl -s -X POST https://umerhassan.pythonanywhere.com/upload \
      -F "token=MeraSecureToken123" \
      -F "version=$NEXT_VERSION" \
      -F "file=@latest_app.zip")

    # 5. Verify and Log
    if [[ "$RESPONSE" == *"success"* ]]; then
        echo "✅ Success: Server Response -> $RESPONSE"
        # Format: YYYY-MM-DD HH:MM:SS VERSION (Mera version ab 3rd column pe save hoga explicit gap ke sath)
        echo "$(date '+%Y-%m-%d %H:%M:%S') $NEXT_VERSION" >> "$LOG_FILE"
        echo "📝 Log updated in $LOG_FILE (Current: $NEXT_VERSION)"
    else
        echo "❌ Deployment Failed!"
        echo "Server Response: $RESPONSE"
    fi

    # Clean up local zip after upload
    if [ -f "latest_app.zip" ]; then
        rm latest_app.zip
    fi
    echo "=========================================="
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
    # GDrive se sirf top-level folders ki list nikalna
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
# 4. TARUX VAULT & SINGLE-SESSION LOCK
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

# Trap definitions
trap_tab_close() {
    echo -e "\n[!] Session Terminated."
    exit
}

trap_prompt_bypass() {
    echo -e "\n[!] Bypass attempt blocked. Closing tab..."
    exit
}

# GLOBAL LOCK: Script start hote hi Ctrl+C ko block kar diya
trap 'trap_prompt_bypass' SIGINT SIGTERM TSTP

# A. First run initialization check
if [ ! -d "$HIDDEN_DIR" ]; then
    mkdir -p "$HIDDEN_DIR"
    if [ -d "$SRC_DIR" ]; then
        cp -r "$SRC_DIR"/. "$HIDDEN_DIR/"
        chmod 700 "$HIDDEN_DIR"
    fi
fi

# B. Tab Duplicate Check (Server already running?)
if pgrep -f "manage.py runserver" > /dev/null 2>&1; then
    clear
    echo "[!] Server already running in another tab. Closing this tab..."
    sleep 1
    exit
fi

# C. Stealth Emoji Prompt (5 Seconds Window)
clear
echo -n "⚙️  "
read -t 5 -s -p "" USER_KEY
echo ""

# D. Mode Selection Logic
if [ "$USER_KEY" = "UKBH" ]; then
    # Anti-bypass trap release for Safe Mode
    trap - SIGINT SIGTERM TSTP
    echo "[+] SAFE MODE ACTIVATED."
    
    # Cloud Sync Initiation via Rclone (Direct Zip Backups Folder)
    echo "[*] Initiating secure sync of Zip Backups to Google Drive..."
    
    if [ -d "$ZIP_BACKUP_SRC" ]; then
        rclone copy "$ZIP_BACKUP_SRC" gdrive:my_projects -P --stats-one-line
        echo "[+] Zip backups sync to cloud completed safely."
    else
        echo "[X] Error: Local Zip Backup directory not found."
    fi
    
    cd "$PARENT_SRC_DIR" 2>/dev/null || cd "$HOME"
else
    # Trap for blocking standard keyboard interrupts during server execution
    trap 'trap_tab_close' SIGINT SIGTERM TSTP

    if [ -d "$HIDDEN_DIR" ]; then
        cd "$HIDDEN_DIR"
        if [ -f "manage.py" ]; then
            # Run server silently in background
            python manage.py runserver > /dev/null 2>&1 &
            SERVER_PID=$!
            
            sleep 1.5
            if kill -0 $SERVER_PID > /dev/null 2>&1; then
                echo "[+] Engine Active. [PID: $SERVER_PID]"
                wait $SERVER_PID
            else
                exit
            fi
        else
            exit
        fi
    fi
fi

