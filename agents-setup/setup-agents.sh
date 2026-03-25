#!/usr/bin/env bash
set -euo pipefail
#
# setup-agents.sh — Provision the 5-agent mini-drama pipeline on a fresh OpenClaw instance.
# Run as root (or with sudo) after OpenClaw is installed and onboarded.
#
# Usage:
#   sudo bash setup-agents.sh
#
# Idempotent: safe to re-run. Skips agents/workspaces/skills that already exist.

OC_HOME="${OPENCLAW_HOME:-/root/.openclaw}"
OC_BIN="$(command -v openclaw 2>/dev/null || echo '/root/.local/share/pnpm/openclaw')"

log() { echo "[setup-agents] $*"; }

# ---------------------------------------------------------------------------
# Agent definitions: id, emoji, identity name, unique skill slug
# ---------------------------------------------------------------------------
declare -A AGENT_EMOJI=(
  [pitch]="💡"
  [writer]="✍️"
  [music]="🎵"
  [thumbnail]="🖼️"
  [packaging]="📦"
)

declare -A AGENT_NAME=(
  [pitch]="Pitch Agent"
  [writer]="Writer Agent"
  [music]="Music Agent"
  [thumbnail]="Thumbnail Agent"
  [packaging]="Packaging Agent"
)

# Unique skill per agent (installed on top of whatever base skills the workspace gets)
declare -A AGENT_SKILL=(
  [pitch]="openclaw-tavily-search"
  [writer]="writing"
  [music]="music-playlist"
  [thumbnail]="image-generation"
  [packaging]="tiktok"
)

AGENTS=(pitch writer music thumbnail packaging)

# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------
if ! command -v "$OC_BIN" &>/dev/null; then
  log "ERROR: openclaw binary not found. Install OpenClaw first."
  exit 1
fi

log "Using openclaw at: $OC_BIN"
log "OpenClaw home: $OC_HOME"

# ---------------------------------------------------------------------------
# Create agents + workspaces
# ---------------------------------------------------------------------------
EXISTING_AGENTS=$("$OC_BIN" agents list --json 2>/dev/null | grep '"id"' | sed 's/.*"id": *"//;s/".*//' || true)

for agent in "${AGENTS[@]}"; do
  if echo "$EXISTING_AGENTS" | grep -qx "$agent"; then
    log "Agent '$agent' already exists — skipping creation."
  else
    WS_DIR="$OC_HOME/workspaces/$agent"
    mkdir -p "$WS_DIR"
    log "Creating agent: $agent (workspace: $WS_DIR)"
    "$OC_BIN" agents add "$agent" \
      --workspace "$WS_DIR" \
      --model "openai/gpt-4o-mini" \
      --non-interactive \
      --json 2>/dev/null || true
  fi
done

# ---------------------------------------------------------------------------
# Set identity (emoji + name) in openclaw.json
# ---------------------------------------------------------------------------
log "Updating agent identities in openclaw.json..."
node -e "
const fs = require('fs');
const configPath = '${OC_HOME}/openclaw.json';
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const identities = {
  pitch:     { name: 'Pitch Agent',     emoji: '💡' },
  writer:    { name: 'Writer Agent',    emoji: '✍️' },
  music:     { name: 'Music Agent',     emoji: '🎵' },
  thumbnail: { name: 'Thumbnail Agent', emoji: '🖼️' },
  packaging: { name: 'Packaging Agent', emoji: '📦' },
};

for (const entry of config.agents.list) {
  if (identities[entry.id]) {
    entry.identity = identities[entry.id];
    entry.name = entry.id;
  }
}
fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
console.log('Identities updated.');
"

# ---------------------------------------------------------------------------
# Install unique skills into each workspace
# ---------------------------------------------------------------------------
for agent in "${AGENTS[@]}"; do
  skill="${AGENT_SKILL[$agent]}"
  ws_dir="$OC_HOME/workspaces/$agent"

  if [ -d "$ws_dir/skills/$skill" ]; then
    log "Skill '$skill' already in $agent workspace — skipping."
  else
    log "Installing skill '$skill' into $agent workspace..."
    (cd "$ws_dir" && oc-skills install "$skill" 2>&1) || \
      log "WARN: Failed to install $skill for $agent (may need manual install)"
  fi
done

# ---------------------------------------------------------------------------
# Also ensure pitch has 'writing' (it was present in the original setup)
# ---------------------------------------------------------------------------
if [ ! -d "$OC_HOME/workspaces/pitch/skills/writing" ]; then
  log "Installing 'writing' skill into pitch workspace..."
  (cd "$OC_HOME/workspaces/pitch" && oc-skills install writing 2>&1) || true
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log ""
log "=== Setup Complete ==="
log ""
"$OC_BIN" agents list --json 2>/dev/null | node -e "
const data = JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));
for (const a of data) {
  if (['pitch','writer','music','thumbnail','packaging'].includes(a.id)) {
    console.log('  ' + (a.identityEmoji||'') + ' ' + a.id + ' -> ' + a.workspace);
  }
}
"
log ""
log "Skills per workspace:"
for agent in "${AGENTS[@]}"; do
  skills=$(ls "$OC_HOME/workspaces/$agent/skills/" 2>/dev/null | tr '\n' ', ' | sed 's/,$//')
  log "  $agent: $skills"
done
log ""
log "Done. Restart the gateway if needed: sudo pkill openclaw-gateway && openclaw gateway start"
