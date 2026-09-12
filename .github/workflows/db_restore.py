name: Database Restore from Google Drive

on:
  workflow_dispatch:
    inputs:
      backup_file_name:
        description: 'Backup file name (e.g. backup_dbname_20260912_153000.enc). Leave empty for LATEST backup.'
        required: false
        default: ''

jobs:
  restore-from-gdrive:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout Code
      uses: actions/checkout@v4

    - name: Setup Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install Python Dependencies
      run: |
        python -m pip install --upgrade pip
        pip install cryptography pymysql sqlalchemy python-dotenv jq

    - name: Install & Setup Rclone
      env:
        RCLONE_CONFIG_DATA: ${{ secrets.RCLONE_CONFIG_DATA }}
      run: |
        sudo apt-get update && sudo apt-get install -y rclone jq
        mkdir -p ~/.config/rclone
        echo "$RCLONE_CONFIG_DATA" > ~/.config/rclone/rclone.conf

    - name: Download Backup File from Google Drive
      run: |
        TARGET_DIR="gdrive:DB_Backups"
        INPUT_FILE="${{ github.event.inputs.backup_file_name }}"

        if [ -n "$INPUT_FILE" ]; then
          echo "📥 Specified backup file requested: $INPUT_FILE"
          FILE_TO_DOWNLOAD="$INPUT_FILE"
        else
          echo "🔍 Searching for the LATEST backup file in Google Drive..."
          FILE_TO_DOWNLOAD=$(rclone lsjson $TARGET_DIR --include "*.enc" | jq -r 'sort_by(.ModTime) | .[-1].Name')
        fi

        if [ -z "$FILE_TO_DOWNLOAD" ] || [ "$FILE_TO_DOWNLOAD" == "null" ]; then
          echo "❌ Error: No valid .enc backup file found in Google Drive!"
          exit 1
        fi

        echo "🚀 Downloading file: $FILE_TO_DOWNLOAD"
        rclone copyto "$TARGET_DIR/$FILE_TO_DOWNLOAD" "./$FILE_TO_DOWNLOAD" --verbose

        if [ ! -f "$FILE_TO_DOWNLOAD" ]; then
          echo "❌ Download failed! File not found locally."
          exit 1
        fi

        echo "SELECTED_FILE=$FILE_TO_DOWNLOAD" >> $GITHUB_ENV
        echo "✅ Download completed: $FILE_TO_DOWNLOAD"

    - name: Execute Database Restore
      env:
        DB_USER: ${{ secrets.DB_USER }}
        DB_PASS: ${{ secrets.DB_PASS }}
        DB_HOST: ${{ secrets.DB_HOST }}
        DB_PORT: ${{ secrets.DB_PORT }}
        DB_NAME: ${{ secrets.DB_NAME }}
        BACKUP_SECRET_KEY: ${{ secrets.BACKUP_SECRET_KEY }}
      run: |
        echo "🔓 Starting Database Restore for file: $SELECTED_FILE"
        python db_backup_manager.py restore "$SELECTED_FILE"

    - name: Workflow Status Summary
      run: |
        echo "🎉 Database Restore Process Finished Successfully!"
