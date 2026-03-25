# ClawDramas

Netflix-style mini-drama catalog with AI-generated thumbnails, critic reviews, and crowd reviews.

## Architecture

- `server/` — FastAPI app (server.py) with Jinja2 templates, static assets, arena/tournament logic
- `agents-setup/` — OpenClaw agent provisioning (5-agent drama pipeline)
- `terraform/` — Tencent Cloud CVM provisioning

## Deploy

### Prerequisites
- A CVM instance (Ubuntu 22.04+) with port 80 open
- SSH key access to the instance
- `.env` file on the server (copy from `.env.example` and fill in values)

### Deploy server code

```bash
SSH_KEY=~/secrets/camus_tke_ssh.pem SERVER=ubuntu@<CVM_IP> ./deploy.sh
```

This rsyncs `server/` to `~/moltbot/` on the CVM, installs deps, and starts the server.

### First-time setup

1. SSH into the server
2. Copy `.env.example` to `~/moltbot/.env` and fill in LLM and Google API keys
3. Run `pip3 install -r ~/moltbot/requirements.txt`
4. Run deploy.sh

### Terraform (optional)

```bash
cd terraform
terraform init && terraform apply
```

This provisions a new CVM instance. After provisioning, run deploy.sh with the output IP.

## Key Details
- `.env` lives on the server only, never committed
- `data/` and `replays/` are server-local runtime data
- Thumbnails are generated via Google Gemini API
- Reviews are generated via any OpenAI-compatible LLM endpoint
