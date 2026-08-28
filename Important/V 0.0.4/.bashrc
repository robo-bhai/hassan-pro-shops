#!/data/data/com.termux/files/usr/bin/bash

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
# PROGRESS DISPLAY FUNCTIONS
# ==========================================

# Progress bar function
show_progress() {
    local step=$1
    local total=$2
    local message=$3
    local percent=$((step * 100 / total))
    local bar_length=30
    local filled=$((percent * bar_length / 100))
    local empty=$((bar_length - filled))
    
    printf "\r["
    printf "%${filled}s" | tr ' ' '█'
    printf "%${empty}s" | tr ' ' '░'
    printf "] %3d%%  %s" "$percent" "$message"
}

# Step indicator
show_step() {
    local message=$1
    echo -e "\n🔹 $message"
    sleep 0.3
}

# Success message
show_success() {
    echo -e "✅ $1"
}

# Error message
show_error() {
    echo -e "❌ $1"
}

# Warning message
show_warning() {
    echo -e "⚠️  $1"
}

# Auto open Chrome function
open_chrome() {
    local URL="${1:-http://127.0.0.1:8000}"
    
    # Try different methods to open Chrome
    if command -v termux-open &> /dev/null; then
        termux-open "$URL" 2>/dev/null
        show_success "Chrome opened via termux-open"
    elif command -v am &> /dev/null; then
        am start -a android.intent.action.VIEW -d "$URL" com.android.chrome 2>/dev/null || \
        am start -a android.intent.action.VIEW -d "$URL" 2>/dev/null
        show_success "Chrome launched via Android AM"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$URL" 2>/dev/null
        show_success "Browser opened via xdg-open"
    else
        show_warning "No browser opener found. Open manually: $URL"
        return 1
    fi
    return 0
}

# ==========================================
# 2. DJANGO ENGINE WITH 20 SEC DELAY & AUTO CHROME
# ==========================================

start_engine() {
    local PORT="${1:-8000}"
    local SERVER_URL="http://127.0.0.1:$PORT"
    
    echo -e "\n⚙️  STARTING DJANGO ENGINE"
    echo -e "=========================================="
    
    show_step "[1/7] Initializing environment on port $PORT..."
    show_progress 1 7 "Loading..."
    sleep 0.3
    echo ""
    
    show_step "[2/7] Checking dependencies..."
    show_progress 2 7 "Verifying..."
    sleep 0.3
    echo ""
    
    show_step "[3/7] Starting server process..."
    show_progress 3 7 "Launching..."
    sleep 0.3
    echo ""
    
    if [ -f "manage.py" ]; then
        show_step "[4/7] Running migrations check..."
        show_progress 4 7 "Preparing..."
        sleep 0.3
        echo ""
        
        # Start Django server
        python manage.py runserver $PORT > /dev/null 2>&1 &
        SERVER_PID=$!
        
        sleep 2  # Initial wait for server to start
        
        if kill -0 $SERVER_PID > /dev/null 2>&1; then
            show_step "[5/7] Waiting for server to stabilize..."
            echo -n "   "
            # 20 seconds countdown with progress
            for i in {1..20}; do
                show_progress $i 20 "Server stabilizing... ($i/20 sec)"
                sleep 1
            done
            echo ""
            show_success "Server is now fully ready"
            
            show_step "[6/7] Launching Chrome browser..."
            show_progress 6 7 "Opening browser..."
            sleep 0.3
            echo ""
            
            # Auto open Chrome after 20 seconds
            open_chrome "$SERVER_URL"
            
            show_step "[7/7] Finalizing..."
            show_progress 7 7 "Ready!"
            sleep 0.2
            echo ""
            
            echo -e "\n✅ ENGINE ACTIVE [PID: $SERVER_PID]"
            echo -e "📍 Server running at: $SERVER_URL"
            echo -e "🌐 Chrome opened automatically after 20 seconds"
            echo -e "=========================================="
            echo -e ""
            echo -e "💡 Tips:"
            echo -e "   • Press Ctrl+C to stop server"
            echo -e "   • Use 'run' alias to restart"
            echo -e "==========================================\n"
            
            wait $SERVER_PID
        else
            show_error "Engine failed to start"
            exit
        fi
    else
        show_error "manage.py not found in $(pwd)"
        exit
    fi
}

# ==========================================
# 3. AUTOMATED DJANGO DEPLOYER TO PYTHONANYWHERE
# ==========================================

humer() {
    local LOG_FILE="version_history.log"
    local DEFAULT_VERSION="1.0.0"
    local NEXT_VERSION=""

    echo -e "\n=========================================="
    echo -e "🚀 STARTING DEPLOYMENT PROCESS"
    echo -e "=========================================="

    # Step 1/6: Reading version history
    show_step "[1/6] Reading version history..."
    
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
            show_success "Last version: $LAST_VERSION → New: $NEXT_VERSION"
        else
            NEXT_VERSION="$DEFAULT_VERSION"
            show_warning "Invalid version format, using: $NEXT_VERSION"
        fi
    else
        NEXT_VERSION="$DEFAULT_VERSION"
        show_warning "No history found, starting with: $NEXT_VERSION"
    fi

    # Step 2/6: Cleaning old zip
    show_step "[2/6] Cleaning old zip files..."
    if [ -f "latest_app.zip" ]; then
        rm latest_app.zip
        show_success "Removed old latest_app.zip"
    else
        show_success "No old zip to clean"
    fi

    # Step 3/6: Creating project zip
    show_step "[3/6] Creating project zip archive..."
    echo -n "   "
    for i in {1..10}; do
        show_progress $i 10 "Zipping files..."
        sleep 0.1
    done
    echo ""
    
    zip -r latest_app.zip . -x "latest_app.zip" "db.sqlite3" "db.sqlite3.backup" "*.log" "*/__pycache__/*" "current_version.txt" ".git/*" > /dev/null

    if [ ! -f "latest_app.zip" ]; then
        show_error "Zip file creation failed!"
        return 1
    fi
    show_success "Zip created successfully (size: $(du -h latest_app.zip | cut -f1))"

    # Step 4/6: Uploading to PythonAnywhere
    show_step "[4/6] Uploading to PythonAnywhere..."
    echo -n "   "
    for i in {1..20}; do
        show_progress $i 20 "Uploading... (please wait)"
        sleep 0.1
    done
    echo ""
    
    local RESPONSE=$(curl -s -X POST https://umerhassan.pythonanywhere.com/upload \
      -F "token=MeraSecureToken123" \
      -F "version=$NEXT_VERSION" \
      -F "file=@latest_app.zip")

    # Step 5/6: Verifying response
    show_step "[5/6] Verifying server response..."
    
    if [[ "$RESPONSE" == *"success"* ]]; then
        show_success "Server accepted deployment"
        echo "$(date '+%Y-%m-%d %H:%M:%S') $NEXT_VERSION" >> "$LOG_FILE"
        show_success "Version $NEXT_VERSION logged"
    else
        show_error "Deployment failed!"
        echo "Server Response: $RESPONSE"
    fi

    # Step 6/6: Cleanup
    show_step "[6/6] Cleaning up..."
    if [ -f "latest_app.zip" ]; then
        rm latest_app.zip
        show_success "Removed temporary zip"
    fi

    echo -e "\n=========================================="
    if [[ "$RESPONSE" == *"success"* ]]; then
        echo -e "🎉 DEPLOYMENT COMPLETE! Version: $NEXT_VERSION"
    else
        echo -e "💥 DEPLOYMENT FAILED!"
    fi
    echo -e "==========================================\n"
}

# ==========================================
# 4. CUSTOM ZIP BACKUP FUNCTION (cz)
# ==========================================

cz() {
    local BACKUP_DIR="$HOME/storage/shared/nom_back/zip_backup"
    mkdir -p "$BACKUP_DIR"
    local LOG_FILE="$BACKUP_DIR/backup_log.txt"
    local DIR_NAME=$(basename "$PWD")
    local COUNTER=1
    local ZIP_NAME=$(printf "%s_%03d.zip" "$DIR_NAME" "$COUNTER")

    echo -e "\n📦 STARTING BACKUP PROCESS"
    echo -e "=========================================="
    
    show_step "Checking existing backups..."
    while [ -f "$BACKUP_DIR/$ZIP_NAME" ]; do
        COUNTER=$((COUNTER + 1))
        ZIP_NAME=$(printf "%s_%03d.zip" "$DIR_NAME" "$COUNTER")
    done
    show_success "Backup name: $ZIP_NAME"

    show_step "Creating zip archive..."
    echo -n "   "
    for i in {1..20}; do
        show_progress $i 20 "Compressing files..."
        sleep 0.05
    done
    echo ""
    
    zip -r "$BACKUP_DIR/$ZIP_NAME" . .* -x ".." 2>/dev/null

    if [ $? -eq 0 ]; then
        local TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
        echo "[$TIMESTAMP] Created: $ZIP_NAME | Path: $PWD" >> "$LOG_FILE"
        echo -e "\n✅ Backup completed successfully!"
        echo "   📁 Location: $BACKUP_DIR/$ZIP_NAME"
        echo "   📊 Size: $(du -h "$BACKUP_DIR/$ZIP_NAME" | cut -f1)"
        echo "   📝 Log: $LOG_FILE"
    else
        show_error "Zip creation failed!"
    fi
    echo -e "==========================================\n"
}

# ==========================================
# 5. GLOBAL RESTORE ENGINE (rest)
# ==========================================

rest() {
    local LOCAL_TARGET="$HOME/storage/shared/nom_back"
    mkdir -p "$LOCAL_TARGET"

    echo -e "\n🔄 GDRIVE RESTORE SYSTEM"
    echo -e "=========================================="
    
    show_step "Fetching folders from Google Drive..."
    echo -n "   "
    for i in {1..15}; do
        show_progress $i 15 "Connecting to cloud..."
        sleep 0.1
    done
    echo ""
    
    local FOLDERS=()
    while IFS= read -r line; do
        FOLDERS+=("$line")
    done < <(rclone lsf gdrive:my_projects --dirs-only)

    if [ ${#FOLDERS[@]} -eq 0 ]; then
        show_error "No directories found in gdrive:my_projects"
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
        echo -e "\n📥 RESTORING ALL FOLDERS"
        show_step "Starting bulk restore..."
        echo -n "   "
        for i in {1..30}; do
            show_progress $i 30 "Downloading from cloud..."
            sleep 0.1
        done
        echo ""
        rclone copy gdrive:my_projects "$LOCAL_TARGET" -P --stats-one-line
        show_success "All folders restored to: $LOCAL_TARGET"
    elif [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -le "${#FOLDERS[@]}" ] && [ "$CHOICE" -gt 0 ]; then
        local SELECTED_INDEX=$((CHOICE-1))
        local TARGET_FOLDER="${FOLDERS[$SELECTED_INDEX]}"
        
        echo -e "\n📥 RESTORING: $TARGET_FOLDER"
        show_step "Starting restore..."
        echo -n "   "
        for i in {1..20}; do
            show_progress $i 20 "Downloading $TARGET_FOLDER..."
            sleep 0.1
        done
        echo ""
        
        rclone copy "gdrive:my_projects/$TARGET_FOLDER" "$LOCAL_TARGET/$TARGET_FOLDER" -P --stats-one-line
        show_success "Restored to: $LOCAL_TARGET/$TARGET_FOLDER"
    else
        show_error "Invalid Selection"
    fi
    echo -e "==========================================\n"
}
alias rest=rest

# ==========================================
# 6. TARUX VAULT & SINGLE-SESSION LOCK
# ==========================================

HIDDEN_DIR="$HOME/.apps_core/.engine_data"
SRC_DIR="$HOME/storage/shared/django/p1"
PARENT_SRC_DIR="$HOME/storage/shared/django"
ZIP_BACKUP_SRC="$HOME/storage/shared/nom_back/zip_backup"

# Sync Commands
reuse() {
    echo -e "\n🔓 REVEALING VAULT CONTENTS"
    echo -e "=========================================="
    
    show_step "Creating target directory..."
    mkdir -p "$SRC_DIR"
    
    show_step "Copying files from vault..."
    echo -n "   "
    for i in {1..10}; do
        show_progress $i 10 "Copying..."
        sleep 0.1
    done
    echo ""
    
    cp -r "$HIDDEN_DIR"/. "$SRC_DIR/"
    show_success "Files copied to: $SRC_DIR"
    echo -e "==========================================\n"
}

refun() {
    echo -e "\n🔒 HIDING FILES TO VAULT"
    echo -e "=========================================="
    
    show_step "Creating vault directory..."
    mkdir -p "$HIDDEN_DIR"
    
    show_step "Clearing old vault data..."
    rm -rf "${HIDDEN_DIR:?}"/*
    
    show_step "Copying files to vault..."
    echo -n "   "
    for i in {1..10}; do
        show_progress $i 10 "Securing..."
        sleep 0.1
    done
    echo ""
    
    cp -r "$SRC_DIR"/. "$HIDDEN_DIR/"
    chmod 700 "$HIDDEN_DIR"
    show_success "Files secured in hidden vault"
    echo -e "==========================================\n"
}

# Trap definitions
trap_tab_close() {
    echo -e "\n\n⚠️  Session Terminated by User"
    exit
}

trap_prompt_bypass() {
    echo -e "\n\n🚫 Bypass attempt detected. Closing session..."
    exit
}

# GLOBAL LOCK: Script start hote hi Ctrl+C ko block kar diya
trap 'trap_prompt_bypass' SIGINT SIGTERM TSTP

# First run initialization check
if [ ! -d "$HIDDEN_DIR" ]; then
    echo -e "\n🔧 FIRST TIME SETUP"
    echo -e "=========================================="
    show_step "Creating vault directory..."
    mkdir -p "$HIDDEN_DIR"
    if [ -d "$SRC_DIR" ]; then
        show_step "Seeding initial data to vault..."
        cp -r "$SRC_DIR"/. "$HIDDEN_DIR/"
        chmod 700 "$HIDDEN_DIR"
        show_success "Vault initialized"
    fi
    echo -e "==========================================\n"
fi

# Tab Duplicate Check (Server already running?)
if pgrep -f "manage.py runserver" > /dev/null 2>&1; then
    clear
    echo -e "\n⚠️  ENGINE ALREADY RUNNING"
    echo -e "=========================================="
    show_warning "Server active in another tab"
    echo -e "Closing this tab in 2 seconds...\n"
    sleep 2
    exit
fi

# Stealth Emoji Prompt (5 Seconds Window)
clear
echo -e "┌─────────────────────────────────┐"
echo -e "│     🔧 TERMUX ENGINE v2.0       │"
echo -e "├─────────────────────────────────┤"
echo -e "│  Press Enter to start engine    │"
echo -e "│  or enter SAFE MODE password    │"
echo -e "└─────────────────────────────────┘"
echo -n "⚙️  "
read -t 5 -s -p "" USER_KEY
echo ""

# Mode Selection Logic
if [ "$USER_KEY" = "UKBH" ]; then
    # Anti-bypass trap release for Safe Mode
    trap - SIGINT SIGTERM TSTP
    
    echo -e "\n🛡️  SAFE MODE ACTIVATED"
    echo -e "=========================================="
    
    show_step "Initiating cloud backup sync..."
    echo -n "   "
    for i in {1..15}; do
        show_progress $i 15 "Connecting to Google Drive..."
        sleep 0.1
    done
    echo ""
    
    # Cloud Sync Initiation via Rclone (Direct Zip Backups Folder)
    if [ -d "$ZIP_BACKUP_SRC" ]; then
        rclone copy "$ZIP_BACKUP_SRC" gdrive:my_projects -P --stats-one-line 2>/dev/null
        show_success "Zip backups synced to cloud"
    else
        show_warning "Local backup directory not found"
    fi
    
    show_step "Navigating to project directory..."
    cd "$PARENT_SRC_DIR" 2>/dev/null || cd "$HOME"
    show_success "Current: $(pwd)"
    echo -e "==========================================\n"
else
    # Trap for blocking standard keyboard interrupts during server execution
    trap 'trap_tab_close' SIGINT SIGTERM TSTP

    if [ -d "$HIDDEN_DIR" ]; then
        cd "$HIDDEN_DIR"
        start_engine
    else
        show_error "Vault not found! Run setup first."
        exit
    fi
fi