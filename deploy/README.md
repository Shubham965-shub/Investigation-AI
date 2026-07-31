# QA deployment (manual, scripted)

Deploys the monorepo to the Azure QA environment (`QA-Lighthouse`):

| Service  | Target |
|----------|--------|
| backend/ | Container App `investigationai-be-qa` (env `investigationai-ds-env`) |
| ds/      | Container App `investigationai-search-agent` (reused; internal-only ingress) |
| frontend/| Static Web App `investigationai-fe-qa-v2` (eastasia, Free) |

## Prerequisites

- `az` (logged in to the STRIDES-RISE-LH-01 subscription), `git`, `node`/`npm`, `jq`, `openssl`
- `psql` (optional — only for the `db-verify` / `db-apply` phases)
- Local `.env` files (git-ignored, the config source of truth):
  - `ds/.env` — all 10 DS vars (DB_*, OPENAI_API_KEY, SEARCH_AGENT_*)
  - `backend/backend/.env` — DB_*, AUTH_PLACEHOLDER_SECRET, pool sizes
  - `frontend/.env` — local dev only; the QA build overrides `VITE_API_BASE_URL`

No local Docker needed — images build in the cloud via `az acr build` (linux/amd64).

## Usage

```bash
./deploy/qa.sh all        # full deploy (everything except db-apply)
./deploy/qa.sh <phase>    # re-run a single phase
./deploy/qa.sh db-apply   # ONLY after explicit DB-owner approval
```

Phases: `preflight snapshot build ds-update ds-internal backend db-verify swa cors frontend verify db-apply`

## Notes

- `ds-internal` is gated: flipping DS ingress to internal cuts the **old** QA stack
  (`investigationai-be-v1`) off from DS. Deliberate — the old stack is being replaced.
- Rollback state is snapshotted to `deploy/.qa-rollback-<tag>.json` (git-ignored).
  DS rollback: restore old image/resources + `az containerapp ingress update --type external`.
  Backend/SWA are new resources — deleting them is a full rollback.
- `star_schema*.sql` are reference-only and never executed by the script.
