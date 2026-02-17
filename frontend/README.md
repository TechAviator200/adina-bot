# Adina Operator Console (Frontend)

This is the React + TypeScript + Vite operator console for **Adina**, a forward-deployed AI SDR agent.

The UI is intentionally lightweight: it acts as an **operator control surface** for triggering workflows (discover, score, draft, dry-run send) and reviewing results, while the backend owns orchestration, integrations, guardrails, and persistence.

> High-level architecture + product context live in the root README:  
> 👉 `../README.md`  
> Backend setup/auth/Gmail persistence details:  
> 👉 `../backend/README.md`

---

## What this UI does

- Connects to the FastAPI backend and calls `/api/*` endpoints
- Shows **Demo Mode** (when enabled) and locks the UI to dry-run workflows
- Provides a simple interface for:
  - lead discovery / upload
  - scoring
  - outreach drafting
  - reply triage
  - (optional) Gmail connect + controlled sends

---

## Requirements

- Node.js 18+ (20 recommended)
- npm

---

## Setup

From the repo root:

```bash
cd frontend
npm install
