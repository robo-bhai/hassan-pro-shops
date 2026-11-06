#!/usr/bin/env bash
# Usage: db_snapshot.sh <out_dir> [previous_total_rows]
set -euo pipefail
OUT="${1:-snapshot}"; PREV_TOTAL="${2:-0}"
rm -rf "$OUT" payload && mkdir -p "$OUT" payload
export MYSQL_PWD="$DB_PASS"
M=(mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -N -B)

# 1) consistent dump incl. routines/triggers/events
mysqldump -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" \
  --single-transaction --quick --routines --triggers --events --hex-blob \
  --default-character-set=utf8mb4 --set-gtid-purged=OFF --column-statistics=0 \
  --no-tablespaces "$DB_NAME" | gzip -9 > payload/db.sql.gz
gzip -t payload/db.sql.gz

# 2) exact row counts per table
TOTAL=0
{
  echo -e "#git\t${GITHUB_SHA:-local}"; echo -e "#run\t${GITHUB_RUN_ID:-0}"; echo -e "#time\t$(date -u +%FT%TZ)"
  for t in $("${M[@]}" -e "SELECT table_name FROM information_schema.tables WHERE table_schema='$DB_NAME' AND table_type='BASE TABLE'"); do
    n=$("${M[@]}" -e "SELECT COUNT(*) FROM \`$DB_NAME\`.\`$t\`")
    echo -e "$t\t$n"
  done
} > payload/manifest.tsv
TOTAL=$(awk -F'\t' '!/^#/{s+=$2} END{print s+0}' payload/manifest.tsv)
echo -e "#total\t$TOTAL" >> payload/manifest.tsv

# 3) encrypt + checksum
tar -cf - payload | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
  -pass env:BACKUP_SECRET_KEY -out "$OUT/snap.tar.enc"
( cd "$OUT" && sha256sum snap.tar.enc > snap.sha256 )
rm -rf payload

# 4) shrink guard -> decides cache key prefix
PREFIX=ok
if [ "$PREV_TOTAL" -gt 0 ] && [ "$TOTAL" -lt $(( PREV_TOTAL * 95 / 100 )) ]; then PREFIX=suspect; fi
echo "prefix=$PREFIX"  >> "${GITHUB_OUTPUT:-/dev/null}"
echo "total=$TOTAL"    >> "${GITHUB_OUTPUT:-/dev/null}"
echo "Snapshot ready: total_rows=$TOTAL prefix=$PREFIX size=$(du -h "$OUT/snap.tar.enc" | cut -f1)"
