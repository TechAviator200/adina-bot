# Adina Bot - Project Memory

## Deployment Architecture
- **Backend**: Render (FastAPI/Python)
- **Frontend**: Vercel (Vite/React)

## Key Fixes Applied

### Production Routing (Frontend)
- Fixed SPA routing by adding rewrite rule to serve `index.html` for all routes
- Added `base: '/'` to `vite.config.ts` for correct asset paths

### Authentication
- Backend uses `x-api-key` header (not JWT Authorization)
- Frontend sends API key via `x-api-key` header in axios interceptor
- Fixed 401 errors by ensuring `VITE_API_KEY` is set at build time on Vercel
- The frontend API key must match the backend `API_KEY` environment variable

### API Client Configuration
- Base URL defaults to `https://adina-bot-backend.onrender.com` if `VITE_API_BASE_URL` not set
- Located in `frontend/src/api/client.ts`

### Database
- Production uses PostgreSQL on Render
- Added `psycopg2-binary` to requirements.txt
- `db.py` rewrites `postgres://` to `postgresql://` for SQLAlchemy 2.x compatibility
- Falls back to SQLite if PostgreSQL connection fails

## Environment Variables

### Backend (Render)
- `API_KEY` - Required for API authentication
- `DATABASE_URL` - PostgreSQL connection string (auto-provided by Render)
- `SERPAPI_API_KEY` - For company discovery feature
- `HUNTER_API_KEY` - For domain contact lookup
- `SNOV_CLIENT_ID` / `SNOV_CLIENT_SECRET` - Alternative contact provider

### Frontend (Vercel)
- `VITE_API_BASE_URL` - Backend URL (defaults to Render URL)
- `VITE_API_KEY` - Must match backend API_KEY (set at build time)

## Testing
- Smoke test script at `scripts/smoke_test.py`
- Run with: `python3 scripts/smoke_test.py`
