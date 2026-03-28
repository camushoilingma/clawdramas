#!/bin/bash
# Restore ClawDramas data (dramas + images) from local to server
# Usage: ./restore.sh [ssh-host]

HOST="${1:-ubuntu@43.157.18.154}"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Restoring to $HOST..."

# Ensure remote dirs exist
ssh -o StrictHostKeyChecking=no "$HOST" "mkdir -p ~/moltbot/data/dramas ~/moltbot/static/images"

# Sync drama JSON files
rsync -avz \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$LOCAL_DIR/data/dramas/" "$HOST:~/moltbot/data/dramas/" 2>&1 | tail -3

# Sync generated images
rsync -avz \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$LOCAL_DIR/static/images/" "$HOST:~/moltbot/static/images/" 2>&1 | tail -3

DRAMA_COUNT=$(ls "$LOCAL_DIR/data/dramas/"*.json 2>/dev/null | wc -l | tr -d ' ')
IMAGE_COUNT=$(ls "$LOCAL_DIR/static/images/"*.jpg 2>/dev/null | wc -l | tr -d ' ')
echo "Restored: $DRAMA_COUNT dramas, $IMAGE_COUNT images"
