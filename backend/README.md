# ADINA Bot Backend

FastAPI backend for the ADINA automated sales outreach system.

## Requirements

- Python 3.11

## Setup

```bash
# Create virtual environment with Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
# From the backend/ directory
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://127.0.0.1:8000`.

Operator console: `http://127.0.0.1:8000/console`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | — | Required. API key for `/api/*` endpoints |
| `DEMO_MODE` | `false` | When `true`, blocks all real Gmail sends (returns 403). Dry-run still works. |
| `FRONTEND_URL` | — | Optional. Extra CORS origin for the frontend |
| `CREDENTIALS_DIR` | `credentials` | Directory for Gmail credential files (created automatically) |
| `GMAIL_DAILY_LIMIT` | `100` | Max emails per day |

For the frontend, set `VITE_DEMO_MODE=true` in `frontend/.env` to show the Demo Mode badge and lock the UI to dry-run only.

## Authentication

All `/api/*` endpoints require an `x-api-key` header matching the `API_KEY` environment variable. Requests without a valid key receive a `401` response.

The following routes are **exempt** (no key required):
- `GET /health`
- `GET /oauth/callback`

### Example

```bash
# Set your key
export API_KEY="my-secret-key"

# Authenticated request
curl -H "x-api-key: $API_KEY" http://127.0.0.1:8000/api/leads

# Health check (no key needed)
curl http://127.0.0.1:8000/health
```

A missing or incorrect key returns:

```json
{"detail": "Invalid or missing API key"}
```

## Gmail Setup

1. Create a Google Cloud project and enable the Gmail API
2. Download OAuth credentials as `gmail_credentials.json` into your `CREDENTIALS_DIR`
3. Connect via the operator console or `POST /api/gmail/connect`

The directory stores two files:
- `gmail_credentials.json` — OAuth client credentials (you provide this)
- `gmail_token.json` — Saved OAuth token (generated after first connect)

## Persistent Storage (Production)

In containerized deployments the filesystem is ephemeral — `gmail_token.json` would be lost on every redeploy, forcing re-authorization.

Mount a persistent volume at `CREDENTIALS_DIR` so both files survive restarts:

```bash
# Docker
docker run -v /host/path/credentials:/app/credentials \
  -e CREDENTIALS_DIR=/app/credentials \
  adina-bot-backend

# Docker Compose
services:
  backend:
    volumes:
      - credentials_data:/app/credentials
    environment:
      - CREDENTIALS_DIR=/app/credentials

volumes:
  credentials_data:
```

```bash
# Fly.io
fly volumes create credentials_data --size 1
# In fly.toml:
# [mounts]
#   source = "credentials_data"
#   destination = "/app/credentials"
# Set CREDENTIALS_DIR=/app/credentials in [env]
```

```bash
# Railway / Render
# Use a persistent disk mount at /data/credentials
# Set CREDENTIALS_DIR=/data/credentials
```

For local development the default (`credentials/` relative to the backend root) works without any extra config.
