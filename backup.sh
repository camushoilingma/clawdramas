#!/bin/bash
# Backup ClawDramas data (dramas + images) from server to local
# Usage: ./backup.sh [ssh-host]

HOST="${1:-ubuntu@43.157.18.154}"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Backing up from $HOST..."

# Sync drama JSON files
rsync -avz --delete \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$HOST:~/moltbot/data/dramas/" "$LOCAL_DIR/data/dramas/" 2>&1 | tail -3

# Sync generated images
rsync -avz --delete \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$HOST:~/moltbot/static/images/" "$LOCAL_DIR/static/images/" 2>&1 | tail -3

DRAMA_COUNT=$(ls "$LOCAL_DIR/data/dramas/"*.json 2>/dev/null | wc -l | tr -d ' ')
IMAGE_COUNT=$(ls "$LOCAL_DIR/static/images/"*.jpg 2>/dev/null | wc -l | tr -d ' ')
echo "Backed up: $DRAMA_COUNT dramas, $IMAGE_COUNT images"
