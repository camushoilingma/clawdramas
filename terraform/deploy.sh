#!/usr/bin/env bash
set -euo pipefail

# Post-Terraform deploy: provisions the new CVM with ClawDramas
# Usage: SSH_KEY=~/secrets/key.pem ./deploy.sh
# Reads the public IP from Terraform output

SSH_KEY="${SSH_KEY:?Set SSH_KEY to your PEM file path}"
IP=$(terraform output -raw public_ip)
SERVER="ubuntu@$IP"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no"

echo "==> Deploying to $SERVER"

# Wait for SSH to be ready
echo "==> Waiting for SSH..."
for i in $(seq 1 30); do
  ssh $SSH_OPTS "$SERVER" "echo ok" 2>/dev/null && break
  sleep 5
done

# Install Python deps
echo "==> Installing system packages"
ssh $SSH_OPTS "$SERVER" "sudo apt-get update -qq && sudo apt-get install -y -qq python3-pip python3-venv"

# Sync server code
echo "==> Syncing server code"
rsync -avz --exclude='__pycache__' --exclude='.env' --exclude='data' --exclude='replays' \
  -e "ssh $SSH_OPTS" \
  "$(dirname "$0")/../server/" "$SERVER:~/moltbot/"

# Install Python requirements
ssh $SSH_OPTS "$SERVER" "cd ~/moltbot && pip3 install -q -r requirements.txt"

echo "==> Done. Set up .env on the server, then run:"
echo "    SSH_KEY=$SSH_KEY SERVER=$SERVER ../deploy.sh"
