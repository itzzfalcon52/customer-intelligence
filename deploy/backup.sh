#!/bin/sh
# Nightly backup of the app data volume to an S3-compatible bucket (R2 or S3).
# Install on the server: sudo snap install aws-cli --classic, then add to crontab:
#   15 3 * * * /home/ubuntu/customer-intelligence/deploy/backup.sh >> /home/ubuntu/ci-backup.log 2>&1
set -eu
cd "$(dirname "$0")"
# Export the settings so the aws command sees the backup credentials.
set -a
. ./.env
set +a
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="/tmp/ci-data-$stamp.tar.gz"
# A consistent copy: SQLite files are copied while writes are paused by a short stop of the api.
docker compose -f docker-compose.yml --env-file .env stop api
docker run --rm -v customer-intelligence_app-data:/data -v /tmp:/out alpine \
  tar czf "/out/$(basename "$archive")" -C /data .
docker compose -f docker-compose.yml --env-file .env start api
aws s3 cp "$archive" "s3://$BACKUP_BUCKET/ci-data/$(basename "$archive")" \
  ${BACKUP_ENDPOINT:+--endpoint-url "$BACKUP_ENDPOINT"}
rm -f "$archive"
echo "backup $stamp done"
