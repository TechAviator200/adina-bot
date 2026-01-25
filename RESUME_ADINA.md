# ADINA Bot - Resume Guide

## Current Status

**Last Updated:** 2026-01-25

### Completed Features
- API key authentication standardized on `x-api-key` header (lowercase)
- `DISABLE_API_KEY_AUTH=true` env var for local dev bypass
- Google CSE lead discovery endpoint (`POST /api/leads/discover`)
- Explicit dotenv loading with absolute paths
- Clear error messages for auth failures

### API Integrations

| Service | Status | Env Var | Notes |
|---------|--------|---------|-------|
| Backend API Auth | Working | `API_KEY` | Set to `adina-local-dev-key` for local dev |
| Google CSE | Maintenance | `GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX` | Returns graceful error, use Hunter.io fallback |
| Hunter.io | Working | `HUNTER_API_KEY` | Use "Pull by Domain" in frontend |

**Note:** Google CSE is currently returning 403 errors. The endpoint gracefully returns a maintenance message. Use the "Pull by Domain" feature (Hunter.io) to add leads manually.

---

## Quick Start

### 1. Start Backend (Port 8000)
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### 2. Start Frontend (Port 5173)
```bash
cd frontend
npm run dev
```

### 3. Test API
```bash
# Health check (no auth)
curl http://127.0.0.1:8000/health

# Get leads (requires auth)
curl -H "x-api-key: adina-local-dev-key" http://127.0.0.1:8000/api/leads

# Discover leads via Google CSE
curl -X POST http://127.0.0.1:8000/api/leads/discover \
  -H "x-api-key: adina-local-dev-key" \
  -H "Content-Type: application/json" \
  -d '{"industry":"beauty","keywords":["brand","operations"]}'
```

---

## Critical Ports

| Service | Port | URL |
|---------|------|-----|
| Backend API | 8000 | http://127.0.0.1:8000 |
| Frontend | 5173 | http://127.0.0.1:5173 |
| API Docs | 8000 | http://127.0.0.1:8000/docs |

---

## Environment Variables

### Backend (`backend/.env`)
```env
API_KEY=adina-local-dev-key
GOOGLE_CSE_API_KEY=<your-google-api-key>
GOOGLE_CSE_CX=<your-search-engine-id>
HUNTER_API_KEY=<your-hunter-api-key>  # Optional
DISABLE_API_KEY_AUTH=false            # Set true for local dev without auth
```

### Frontend (`frontend/.env`)
```env
VITE_API_BASE_URL=
VITE_API_KEY=adina-local-dev-key
```

---

## Before You Go Live

1. **Enable Google Custom Search API**
   - Go to: https://console.cloud.google.com/apis/library/customsearch.googleapis.com
   - Click "Enable"

2. **Add Hunter.io API Key** (if using lead pull feature)
   - Get key from: https://hunter.io/api
   - Add `HUNTER_API_KEY=<key>` to `backend/.env`

3. **Generate secure API key for production**
   - Replace `adina-local-dev-key` with a long random string
   - Update both `backend/.env` and `frontend/.env`

---

## Next Feature: Automated LinkedIn Outreach

Planned implementation:
- LinkedIn profile scraping via Proxycurl or similar
- Connection request automation
- Message sequencing with follow-ups
- Integration with existing lead scoring

---

## File Structure

```
adina-bot/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + endpoints
│   │   ├── settings.py      # Pydantic settings + dotenv
│   │   ├── schemas.py       # Request/response models
│   │   ├── models.py        # SQLAlchemy models
│   │   └── agent/           # AI agents (scoring, outbound, responses)
│   ├── services/
│   │   ├── google_cse_service.py  # Google CSE integration
│   │   └── hunter_service.py      # Hunter.io integration
│   ├── .env                 # Environment variables
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   └── api/client.ts    # Axios client with x-api-key header
│   ├── .env                 # Frontend env vars
│   └── package.json
└── RESUME_ADINA.md          # This file
```

---

## Troubleshooting

### "Invalid API key" error
- Restart backend after changing `.env`
- Ensure `API_KEY` in backend matches `VITE_API_KEY` in frontend

### "Google CSE API 403" error
- Enable Custom Search API in Google Cloud Console
- Wait 2-3 minutes for propagation

### "Hunter API 401" error
- Add valid `HUNTER_API_KEY` to `backend/.env`
- Restart backend
