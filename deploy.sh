#!/usr/bin/env bash
set -euo pipefail

# Deploy ClawDramas to a CVM server
# Usage: SSH_KEY=~/secrets/key.pem SERVER=ubuntu@1.2.3.4 ./deploy.sh

SSH_KEY="${SSH_KEY:?Set SSH_KEY to your PEM file path}"
SERVER="${SERVER:?Set SERVER to user@host}"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no"

echo "==> Syncing server/ to $SERVER:~/moltbot/"
rsync -avz --exclude='.env' --exclude='__pycache__' --exclude='data' --exclude='replays' --exclude='.venv' \
  -e "ssh $SSH_OPTS" \
  "$(dirname "$0")/server/" "$SERVER:~/moltbot/"

echo "==> Restarting server"
ssh $SSH_OPTS "$SERVER" bash -s <<'EOF'
sudo pkill -f 'python3.*server.py' 2>/dev/null || true
sleep 2
cd ~/moltbot
pip3 install -q -r requirements.txt 2>/dev/null || true
sudo nohup python3 -u server.py > /dev/null 2>&1 &
sleep 3
STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/)
echo "Health check: HTTP $STATUS"
[ "$STATUS" = "200" ] && echo "Deploy OK" || echo "DEPLOY FAILED"
EOF
