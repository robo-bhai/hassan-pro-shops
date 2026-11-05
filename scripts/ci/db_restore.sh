#!/usr/bin/env bash
# Usage: db_restore.sh <snapshot_dir>   (never drops anything; DB must be empty)
set -euo pipefail
IN="${1:-snapshot}"
export MYSQL_PWD="$DB_PASS"
M=(mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -N -B)

# ---- Purane workflow ka local cache (cloud_data_dump.sql.gz) -> ek baar import ----
if [ ! -f "$IN/snap.tar.enc" ] && [ -f cloud_data_dump.sql.gz ]; then
  echo "Naya snapshot nahi mila; purane GitHub cache (cloud_data_dump.sql.gz) se load kar raha hoon."
  gzip -t cloud_data_dump.sql.gz
  EXISTING=$(mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME'")
  if [ "$EXISTING" -ne 0 ]; then echo "::error::Target DB khali nahi ($EXISTING tables). Abort."; exit 1; fi
  gunzip -c cloud_data_dump.sql.gz | mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME"
  echo "Legacy cache load ho gaya. Is run ke aakhir mein naye format ka snapshot ban jayega."
  exit 0
fi

if [ ! -f "$IN/snap.tar.enc" ]; then
  if [ "${BOOTSTRAP_EMPTY:-false}" = "true" ]; then
    echo "No snapshot; bootstrap_empty=true -> starting with empty DB"; exit 0
  fi
  echo "::error::No snapshot found in GitHub Cache. Refusing to start on an empty DB."; exit 1
fi

( cd "$IN" && sha256sum -c snap.sha256 )
rm -rf payload
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_SECRET_KEY -in "$IN/snap.tar.enc" | tar -xf -
gzip -t payload/db.sql.gz

EXISTING=$("${M[@]}" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME'")
if [ "$EXISTING" -ne 0 ]; then echo "::error::Target DB is not empty ($EXISTING tables). Aborting without dropping."; exit 1; fi

gunzip -c payload/db.sql.gz | mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME"

# verify every table's row count against manifest
FAIL=0
while IFS=$'\t' read -r t n; do
  case "$t" in \#*) continue;; esac
  got=$("${M[@]}" -e "SELECT COUNT(*) FROM \`$DB_NAME\`.\`$t\`")
  [ "$got" = "$n" ] || { echo "::error::Row mismatch $t expected=$n got=$got"; FAIL=1; }
done < payload/manifest.tsv
[ "$FAIL" = 0 ] || exit 1
echo "total=$(awk -F'\t' '$1=="#total"{print $2}' payload/manifest.tsv)" >> "${GITHUB_OUTPUT:-/dev/null}"
rm -rf payload
echo "Restore verified."
