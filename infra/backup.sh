#!/usr/bin/env sh
# نسخة احتياطية يومية مشفّرة لقاعدة البيانات
set -eu
STAMP=$(date +%Y%m%d-%H%M%S)
OUT_DIR="${BACKUP_DIR:-/backups}"
mkdir -p "$OUT_DIR"
pg_dump --no-owner --format=custom "$DATABASE_URL" \
  | gpg --batch --yes --symmetric --cipher-algo AES256 \
        --passphrase "$BACKUP_PASSPHRASE" \
        -o "$OUT_DIR/mobde3-$STAMP.dump.gpg"
# الاحتفاظ بآخر ١٤ نسخة فقط
ls -1t "$OUT_DIR"/mobde3-*.dump.gpg | tail -n +15 | xargs -r rm --
