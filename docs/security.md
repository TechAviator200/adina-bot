# Security Documentation

## Scope

Adina is a **single-tenant, forward-deployed operator tool** — not a multi-tenant SaaS product. The security controls documented here are appropriate for this scope. This document is honest about what is and isn't covered.

## Threat model & assumptions

### In scope

| Threat | Mitigation | Status |
|--------|-----------|--------|
| Secrets committed to git | `.gitignore` blocks `.env`, `credentials/`, token files; gitleaks runs in CI | Active |
| Vulnerable dependencies (Python) | `pip-audit` in CI; Dependabot weekly PRs | Active |
| Vulnerable dependencies (JS) | `npm audit` in CI; Dependabot weekly PRs | Active |
| Common Python security anti-patterns | `bandit` static analysis in CI | Active |
| Semantic code vulnerabilities | CodeQL (Python + JS/TS) on push, PR, and weekly schedule | Active |
| Unauthorized API access | `x-api-key` middleware on all `/api/*` endpoints | Active |
| Accidental mass email sends | Hard-coded 100/day cap; operator approval gate; demo mode | Active |
| Stale dependencies with known CVEs | Dependabot automated PRs (pip, npm, GitHub Actions) | Active |

### Out of scope (acknowledged gaps)

| Gap | Why it's acceptable now | What changes for production |
|-----|------------------------|----------------------------|
| API key visible in browser bundle | Single operator — the person with the key is the deployer | Move to server-side sessions or OAuth |
| No per-user auth or RBAC | Single operator | Add SSO + role-based access |
| No audit log | Operator is the only user | Structured audit log with immutable storage |
| `DISABLE_API_KEY_AUTH` not enforced | Documented as dev-only | Add runtime environment check (`NODE_ENV` / deploy flag) |
| No rate limiting beyond email cap | Single operator, low traffic | Per-key rate limiting via middleware or API gateway |
| Gmail OAuth tokens on ephemeral disk | Render free tier limitation | Use encrypted secret store (Vault, AWS Secrets Manager) |
| No HTTPS certificate pinning | Standard TLS via Render/Vercel | Pin certs if operating in hostile network environments |
| No CSP headers on frontend | SPA served from Vercel CDN | Add Content-Security-Policy headers |

## Handling of secrets and credentials

### Where secrets live

| Secret | Location | Rotation policy |
|--------|----------|----------------|
| `API_KEY` | Render env var (backend), Vercel env var (frontend build) | Manual; rotate if compromised |
| `DATABASE_URL` | Render auto-provisioned | Managed by Render |
| `HUNTER_API_KEY` | Render env var | Per vendor policy |
| `SERPAPI_API_KEY` | Render env var | Per vendor policy |
| `SNOV_CLIENT_ID` / `SNOV_CLIENT_SECRET` | Render env var | Per vendor policy |
| Gmail OAuth tokens | `credentials/` directory (gitignored) | Refreshed automatically by google-auth |

### What is gitignored

```
.env, *.env.local, .env.*.local     # All environment files
credentials/                          # Gmail OAuth tokens
*.json (except package/tsconfig)      # Prevents accidental credential JSON commits
*.db, *.sqlite3                       # Local databases
```

### What CI checks for

- **gitleaks** scans the full git history on every push for patterns matching API keys, tokens, passwords, and other secret formats.
- If gitleaks flags a false positive, add the pattern to a `.gitleaksignore` file (do not disable the check).

## Outbound action safeguards

Adina sends real emails via the operator's Gmail account. Safeguards prevent accidental damage:

1. **Approval gate.** No email is sent unless the operator explicitly approves it. The status flow is: `new → qualified → drafted → approved → sent`. Emails can only be sent from the `approved` state.

2. **Daily cap.** The backend enforces a hard limit of 100 emails per day via the `DailyEmailCount` model. This is checked server-side before every send and cannot be bypassed from the frontend.

3. **Demo mode.** Setting `DEMO_MODE=true` blocks all real sends and returns a 403. Useful for testing the full pipeline without risk.

4. **Batch limits.** Batch send endpoints cap at 25 emails per request, and respect the daily 100 cap.

5. **No autonomous sending.** There is no cron job or background worker that sends emails. Every send is operator-initiated.

## Untrusted input boundaries

### CSV upload

The `POST /api/leads/upload` endpoint accepts CSV files from the operator. The backend:
- Parses with Python's `csv` module (not `eval` or similar)
- Normalizes header names to known fields
- Deduplicates against existing leads by company name/website
- Does not execute any content from the CSV

### External API responses

Data from Hunter.io, Snov.io, and SerpAPI is stored in the database but:
- Is never executed as code
- Is rendered in the React frontend via JSX (auto-escaped by React)
- Is not interpolated into shell commands or SQL (SQLAlchemy parameterizes all queries)

### Reply classification

The response agent classifies inbound email text using keyword matching. The input is the email body (a string). It is:
- Not passed to `eval()` or any code execution path
- Matched against static keyword lists
- Used to select a pre-written template, not to generate arbitrary output

### Prompt injection

The current system does not use LLMs for any agent logic. Scoring, drafting, and reply classification are all deterministic (keyword/template-based). There is no prompt-injection attack surface in the current architecture. If LLM-assisted drafting is added in the future, input sanitization and output constraints would need to be implemented at that boundary.

## Automated security pipeline

| Check | Tool | Trigger | Scope |
|-------|------|---------|-------|
| Secret scanning | gitleaks | push, PR | Full git history |
| Python CVE scan | pip-audit | push, PR | `backend/requirements.txt` |
| Python static analysis | bandit | push, PR | `backend/app/` |
| Frontend dep audit | npm audit | push, PR | `frontend/` |
| Semantic analysis | CodeQL | push, PR, weekly | Python, JS/TS |
| Dependency updates | Dependabot | weekly | pip, npm, GitHub Actions |
| Syntax check | compileall | push, PR | `backend/app/` |
| Build check | vite build | push, PR | `frontend/` |

## What remains out of scope for this portfolio repo

This is a portfolio project demonstrating forward-deployed AI engineering. The following are explicitly not implemented and would be required for a real customer deployment:

- **SOC 2 / compliance frameworks.** No compliance controls, evidence collection, or policy documentation beyond this file.
- **Penetration testing.** No formal pentest has been conducted.
- **Incident response plan.** No runbook for security incidents.
- **Data retention / deletion policy.** Lead data persists indefinitely in PostgreSQL.
- **Encryption at rest.** Relies on Render's infrastructure-level encryption.
- **Multi-region / disaster recovery.** Single-region deployment on Render free tier.
- **WAF / DDoS protection.** No web application firewall or DDoS mitigation beyond what Render/Vercel provide by default.

These are documented here as acknowledgment, not oversight. Each would be addressed in sequence during production hardening for a paying customer.
