#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy/qa.sh — Manual scripted deploy of the InvestigationAI
#  monorepo to the Azure QA environment (QA-Lighthouse).
#
#    backend/  → new Container App  investigationai-be-qa
#    ds/       → existing Container App investigationai-search-agent
#                (new image, bumped resources, internal-only ingress)
#    frontend/ → new Static Web App investigationai-fe-qa-v2
#
#  Config source: each service's local .env file (git-ignored):
#    ds/.env               — all 10 DS vars (required)
#    backend/backend/.env  — backend vars (required)
#    frontend/.env         — local dev only; the QA build overrides
#                            VITE_API_BASE_URL via process env
#  Deploy-derived values always win over .env for:
#    DS_SERVICE_BASE_URL (DS internal FQDN), CORS_ORIGINS (SWA host),
#    VITE_API_BASE_URL (backend FQDN).
#
#  Usage:
#    ./deploy/qa.sh all          # everything except db-apply
#    ./deploy/qa.sh <phase>      # re-run a single phase
#    ./deploy/qa.sh db-apply     # ONLY after DB-owner approval
#
#  Phases: preflight snapshot build ds-update ds-internal backend
#          db-verify swa cors frontend verify db-apply
# ─────────────────────────────────────────────────────────────
set -euo pipefail
# NEVER enable `set -x` here — secrets pass through shell variables.

# ── Colors / helpers (style borrowed from ds/deploy.sh) ───────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}ℹ ${NC} $*"; }
success() { echo -e "${GREEN}✔ ${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠ ${NC} $*"; }
error()   { echo -e "${RED}✖ ${NC} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}\n"; }
confirm() {
    local prompt="${1:-Continue?}"
    echo -en "${YELLOW}${prompt} [y/N]: ${NC}"
    read -r response
    [[ "$response" =~ ^[Yy]$ ]]
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Constants (env-overridable) ───────────────────────────────
SUBSCRIPTION="${SUBSCRIPTION:-16434d97-76c8-4357-b11d-05e42e1e1e49}"
RG="${RG:-QA-Lighthouse}"
ACR="${ACR:-investigationaiacr}"
ACR_SERVER="$ACR.azurecr.io"
ENV_NAME="${ENV_NAME:-investigationai-ds-env}"
DS_APP="${DS_APP:-investigationai-search-agent}"
BE_APP="${BE_APP:-investigationai-be-qa}"
SWA_NAME="${SWA_NAME:-investigationai-fe-qa-v2}"
SWA_LOCATION="${SWA_LOCATION:-eastasia}"
TAG="${TAG:-$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)}"
DS_IMAGE="$ACR_SERVER/investigationai-search-agent:$TAG"
BE_IMAGE="$ACR_SERVER/investigationai-backend:$TAG"

DS_ENV_FILE="$REPO_ROOT/ds/.env"
BE_ENV_FILE="$REPO_ROOT/backend/backend/.env"
SNAPSHOT_FILE="$REPO_ROOT/deploy/.qa-rollback-$TAG.json"

DS_REQUIRED_VARS=(DB_HOST DB_NAME DB_USER DB_PASSWORD DB_PORT
                  DB_POOL_MIN_SIZE DB_POOL_MAX_SIZE OPENAI_API_KEY
                  SEARCH_AGENT_HOST SEARCH_AGENT_PORT)
BE_REQUIRED_VARS=(DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
                  DB_POOL_MIN_SIZE DB_POOL_MAX_SIZE AUTH_PLACEHOLDER_SECRET)

# ── .env parsing ──────────────────────────────────────────────
# Whitelist parser: only NAME=VALUE lines, no `source` of arbitrary
# code, values never echoed. Populates variables with the given prefix.
load_env_file() {
    local file="$1" prefix="$2" line key value
    [[ -f "$file" ]] || { error "Missing env file: $file"; return 1; }
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ ^[[:space:]]*$ ]] && continue
        [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
        key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
        # strip surrounding quotes if present
        value="${value%$'\r'}"
        if [[ "$value" =~ ^\"(.*)\"$ ]] || [[ "$value" =~ ^\'(.*)\'$ ]]; then
            value="${BASH_REMATCH[1]}"
        fi
        printf -v "${prefix}${key}" '%s' "$value"
    done < "$file"
}

require_vars() {
    local prefix="$1"; shift
    local missing=0 v ref
    for v in "$@"; do
        ref="${prefix}${v}"
        if [[ -z "${!ref:-}" ]]; then error "  missing: $v"; missing=1; fi
    done
    return $missing
}

get_fqdn() {
    az containerapp show -n "$1" -g "$RG" \
        --query properties.configuration.ingress.fqdn -o tsv
}

# ── Phases ────────────────────────────────────────────────────

phase_preflight() {
    header "Preflight"
    local missing=0
    for cmd in az git node npm jq openssl; do
        command -v "$cmd" &>/dev/null || { error "$cmd not installed"; missing=1; }
    done
    [[ $missing -eq 0 ]] || exit 1

    az account show &>/dev/null || { error "Not logged into Azure CLI (az login)"; exit 1; }
    az account set --subscription "$SUBSCRIPTION"
    success "Azure: $(az account show --query name -o tsv) / RG $RG"

    info "Validating $DS_ENV_FILE"
    load_env_file "$DS_ENV_FILE" DSENV_
    require_vars DSENV_ "${DS_REQUIRED_VARS[@]}" \
        || { error "ds/.env is incomplete"; exit 1; }
    success "ds/.env has all ${#DS_REQUIRED_VARS[@]} required vars"

    info "Validating $BE_ENV_FILE"
    load_env_file "$BE_ENV_FILE" BEENV_
    require_vars BEENV_ "${BE_REQUIRED_VARS[@]}" \
        || { error "backend/backend/.env is incomplete"; exit 1; }
    success "backend/backend/.env has all ${#BE_REQUIRED_VARS[@]} required vars"

    success "Deploying tag: $TAG"
}

phase_snapshot() {
    header "Snapshot (rollback state)"
    az containerapp show -n "$DS_APP" -g "$RG" --query "{
        image: properties.template.containers[0].image,
        cpu: properties.template.containers[0].resources.cpu,
        memory: properties.template.containers[0].resources.memory,
        minReplicas: properties.template.scale.minReplicas,
        maxReplicas: properties.template.scale.maxReplicas,
        ingressExternal: properties.configuration.ingress.external,
        fqdn: properties.configuration.ingress.fqdn
    }" -o json > "$SNAPSHOT_FILE"
    success "DS app state saved to $SNAPSHOT_FILE"
    jq . "$SNAPSHOT_FILE"
}

phase_build() {
    header "Build images in ACR (linux/amd64, cloud build)"
    info "Backend → $BE_IMAGE"
    az acr build --registry "$ACR" --platform linux/amd64 \
        --image "investigationai-backend:$TAG" "$REPO_ROOT/backend"
    success "Backend image built"

    info "DS → $DS_IMAGE (heavy image — LibreOffice + ML deps, this takes a while)"
    az acr build --registry "$ACR" --platform linux/amd64 \
        --image "investigationai-search-agent:$TAG" "$REPO_ROOT/ds"
    success "DS image built"
}

phase_ds_update() {
    header "DS: sync ds/.env + new image (ingress still external)"
    load_env_file "$DS_ENV_FILE" DSENV_

    info "Syncing secrets from ds/.env → $DS_APP"
    az containerapp secret set -n "$DS_APP" -g "$RG" --secrets \
        db-host="$DSENV_DB_HOST" \
        db-port="$DSENV_DB_PORT" \
        db-name="$DSENV_DB_NAME" \
        db-user="$DSENV_DB_USER" \
        db-password="$DSENV_DB_PASSWORD" \
        db-pool-min-size="$DSENV_DB_POOL_MIN_SIZE" \
        db-pool-max-size="$DSENV_DB_POOL_MAX_SIZE" \
        openai-api-key="$DSENV_OPENAI_API_KEY" \
        >/dev/null
    success "Secrets synced"

    info "Updating image/resources: $DS_IMAGE (1.0 vCPU / 2Gi / minReplicas 1)"
    az containerapp update -n "$DS_APP" -g "$RG" \
        --image "$DS_IMAGE" \
        --cpu 1.0 --memory 2.0Gi \
        --min-replicas 1 --max-replicas 3 \
        --set-env-vars SEARCH_AGENT_HOST=0.0.0.0 SEARCH_AGENT_PORT=8001 \
        >/dev/null
    success "DS app updated"

    local ds_ext_fqdn
    ds_ext_fqdn=$(get_fqdn "$DS_APP")
    info "Waiting for new revision to serve https://$ds_ext_fqdn/docs (image pull can take minutes)"
    curl -fsS --retry 40 --retry-delay 10 --retry-all-errors \
        "https://$ds_ext_fqdn/docs" >/dev/null
    success "DS /docs responds on the new revision"
    az containerapp revision list -n "$DS_APP" -g "$RG" \
        --query "[?properties.active].{rev:name,health:properties.healthState,running:properties.runningState,traffic:properties.trafficWeight}" -o table
}

phase_ds_internal() {
    header "DS: flip ingress to internal-only"
    warn "This DISCONNECTS the old QA stack: investigationai-be-v1 calls DS via its"
    warn "external FQDN and will lose access the moment ingress goes internal."
    confirm "Flip $DS_APP ingress to internal?" || { error "Aborted."; exit 1; }

    az containerapp ingress update -n "$DS_APP" -g "$RG" --type internal >/dev/null
    local ds_internal_fqdn
    ds_internal_fqdn=$(get_fqdn "$DS_APP")
    success "DS internal FQDN: $ds_internal_fqdn"
}

phase_backend() {
    header "Backend: create/update $BE_APP"
    load_env_file "$BE_ENV_FILE" BEENV_

    local ds_internal_fqdn acr_pwd
    ds_internal_fqdn=$(get_fqdn "$DS_APP")
    if [[ "$ds_internal_fqdn" != *".internal."* ]]; then
        warn "DS ingress is still EXTERNAL ($ds_internal_fqdn) — run 'ds-internal' first"
        confirm "Wire backend to the external DS FQDN anyway?" || exit 1
    fi

    if [[ -n "${BEENV_DS_SERVICE_BASE_URL:-}" ]]; then
        warn "Overriding DS_SERVICE_BASE_URL from .env with https://$ds_internal_fqdn"
    fi
    if [[ -n "${BEENV_CORS_ORIGINS:-}" ]]; then
        warn "Overriding CORS_ORIGINS from .env — real value is set in the 'cors' phase"
    fi

    acr_pwd=$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)

    info "Creating/updating container app $BE_APP in $ENV_NAME"
    az containerapp create -n "$BE_APP" -g "$RG" \
        --environment "$ENV_NAME" \
        --image "$BE_IMAGE" \
        --registry-server "$ACR_SERVER" \
        --registry-username "$ACR" \
        --registry-password "$acr_pwd" \
        --ingress external --target-port 8000 \
        --cpu 0.5 --memory 1.0Gi \
        --min-replicas 1 --max-replicas 2 \
        --secrets \
            db-host="$BEENV_DB_HOST" \
            db-port="$BEENV_DB_PORT" \
            db-name="$BEENV_DB_NAME" \
            db-user="$BEENV_DB_USER" \
            db-password="$BEENV_DB_PASSWORD" \
            auth-placeholder-secret="$BEENV_AUTH_PLACEHOLDER_SECRET" \
        --env-vars \
            DS_SERVICE_BASE_URL="https://$ds_internal_fqdn" \
            DS_SERVICE_TIMEOUT_SECONDS="${BEENV_DS_SERVICE_TIMEOUT_SECONDS:-230}" \
            CORS_ORIGINS="https://placeholder.invalid" \
            AUTH_PLACEHOLDER_SECRET=secretref:auth-placeholder-secret \
            DB_HOST=secretref:db-host \
            DB_PORT=secretref:db-port \
            DB_NAME=secretref:db-name \
            DB_USER=secretref:db-user \
            DB_PASSWORD=secretref:db-password \
            DB_POOL_MIN_SIZE="${BEENV_DB_POOL_MIN_SIZE:-1}" \
            DB_POOL_MAX_SIZE="${BEENV_DB_POOL_MAX_SIZE:-10}" \
        >/dev/null

    local be_fqdn
    be_fqdn=$(get_fqdn "$BE_APP")
    info "Waiting for https://$be_fqdn/api/health"
    curl -fsS --retry 30 --retry-delay 5 --retry-all-errors \
        "https://$be_fqdn/api/health" >/dev/null
    success "Backend live: https://$be_fqdn"
}

phase_db_verify() {
    header "DB: read-only table existence check ($RG / qa-lighthouse-db)"
    load_env_file "$DS_ENV_FILE" DSENV_

    if ! command -v psql &>/dev/null; then
        warn "psql not installed — skipping. Alternative: run the check from inside"
        warn "the backend container:  az containerapp exec -n $BE_APP -g $RG"
        return 0
    fi

    local sql="
SELECT t AS table_name, to_regclass('public.'||t) IS NOT NULL AS exists
FROM unnest(ARRAY[
  't_deviations_vector_test','t_deviations_summary',
  'fact_qms_event','dim_event','dim_investigator','dim_rci','dim_product',
  'users','roles','api_call_trails',
  'investigation_problem_statements','investigation_evidence_items',
  'investigation_questionnaire_items','investigation_rci_sections',
  'investigation_rci_tasks'
]) AS t;"

    if ! PGPASSWORD="$DSENV_DB_PASSWORD" psql \
        "host=$DSENV_DB_HOST port=$DSENV_DB_PORT dbname=$DSENV_DB_NAME user=$DSENV_DB_USER sslmode=require connect_timeout=10" \
        -v ON_ERROR_STOP=1 -P pager=off -c "$sql"; then
        warn "Could not reach the DB from this machine (likely firewall)."
        warn "Options: add a temporary firewall rule for your IP on qa-lighthouse-db,"
        warn "or run the check from inside the backend container via az containerapp exec."
        return 1
    fi
    info "Expectations: t_deviations_* and fact/dim tables should EXIST (never create them here)."
    info "If users/roles/api_call_trails or investigation_* are missing → get DB-owner"
    info "approval, then run:  ./deploy/qa.sh db-apply"
}

phase_db_apply() {
    header "DB: apply schema.sql + generated_content.sql (GATED)"
    warn "These files carry 'DO NOT RUN WITHOUT EXPLICIT APPROVAL' headers."
    confirm "Has the DB owner EXPLICITLY approved applying schema.sql + generated_content.sql?" \
        || { error "Aborted — get approval first."; exit 1; }

    command -v psql &>/dev/null || { error "psql required for db-apply"; exit 1; }
    load_env_file "$DS_ENV_FILE" DSENV_
    local conn="host=$DSENV_DB_HOST port=$DSENV_DB_PORT dbname=$DSENV_DB_NAME user=$DSENV_DB_USER sslmode=require"

    # generated_content.sql has FKs to dim_event — refuse to run without it.
    local dim_event_exists
    dim_event_exists=$(PGPASSWORD="$DSENV_DB_PASSWORD" psql "$conn" -tA \
        -c "SELECT to_regclass('public.dim_event') IS NOT NULL;")
    [[ "$dim_event_exists" == "t" ]] \
        || { error "dim_event does not exist — star schema missing; do NOT proceed."; exit 1; }

    info "Applying backend/backend/db/schema.sql (idempotent)"
    PGPASSWORD="$DSENV_DB_PASSWORD" psql "$conn" -v ON_ERROR_STOP=1 \
        -f "$REPO_ROOT/backend/backend/db/schema.sql"
    info "Applying backend/backend/db/generated_content.sql (idempotent)"
    PGPASSWORD="$DSENV_DB_PASSWORD" psql "$conn" -v ON_ERROR_STOP=1 \
        -f "$REPO_ROOT/backend/backend/db/generated_content.sql"
    success "Schema files applied. (star_schema*.sql are reference-only — never applied.)"
}

phase_swa() {
    header "SWA: create $SWA_NAME"
    if az staticwebapp show -n "$SWA_NAME" -g "$RG" &>/dev/null; then
        info "SWA already exists — skipping create"
    else
        az staticwebapp create -n "$SWA_NAME" -g "$RG" \
            --location "$SWA_LOCATION" --sku Free >/dev/null
        success "SWA created"
    fi
    local swa_host
    swa_host=$(az staticwebapp show -n "$SWA_NAME" -g "$RG" --query defaultHostname -o tsv)
    success "SWA hostname: https://$swa_host"
}

phase_cors() {
    header "Backend: set CORS_ORIGINS to the SWA origin"
    local swa_host
    swa_host=$(az staticwebapp show -n "$SWA_NAME" -g "$RG" --query defaultHostname -o tsv)
    az containerapp update -n "$BE_APP" -g "$RG" \
        --set-env-vars CORS_ORIGINS="https://$swa_host" >/dev/null
    success "CORS_ORIGINS = https://$swa_host"
}

phase_frontend() {
    header "Frontend: build + deploy to SWA"
    local be_fqdn swa_host swa_token api_url
    be_fqdn=$(get_fqdn "$BE_APP")
    swa_host=$(az staticwebapp show -n "$SWA_NAME" -g "$RG" --query defaultHostname -o tsv)
    swa_token=$(az staticwebapp secrets list -n "$SWA_NAME" -g "$RG" \
        --query properties.apiKey -o tsv)
    api_url="${VITE_API_BASE_URL:-https://$be_fqdn/api}"

    info "Building with VITE_API_BASE_URL=$api_url (process env beats frontend/.env)"
    ( cd "$REPO_ROOT/frontend" && npm ci && VITE_API_BASE_URL="$api_url" npm run build )

    # Assert the QA URL got baked in and localhost did not leak.
    grep -rql "$be_fqdn" "$REPO_ROOT/frontend/dist/assets" \
        || { error "API URL not baked into bundle!"; exit 1; }
    if grep -rql "localhost:8000" "$REPO_ROOT/frontend/dist/assets"; then
        error "localhost:8000 leaked into the bundle!"; exit 1
    fi
    [[ -f "$REPO_ROOT/frontend/dist/staticwebapp.config.json" ]] \
        || { error "staticwebapp.config.json missing from dist/"; exit 1; }
    success "Bundle checks passed"

    info "Deploying dist/ to $SWA_NAME (production environment)"
    ( cd "$REPO_ROOT/frontend" && npx --yes @azure/static-web-apps-cli@2 deploy ./dist \
        --deployment-token "$swa_token" --env production )
    success "Frontend live: https://$swa_host"
}

phase_verify() {
    header "End-to-end verification"
    local be_fqdn swa_host ds_fqdn
    be_fqdn=$(get_fqdn "$BE_APP")
    ds_fqdn=$(get_fqdn "$DS_APP")
    swa_host=$(az staticwebapp show -n "$SWA_NAME" -g "$RG" --query defaultHostname -o tsv 2>/dev/null || echo "")

    info "1. Backend health"
    curl -fsS "https://$be_fqdn/api/health" && echo ""

    info "2. Backend → DS internal reachability + TLS (via containerapp exec)"
    az containerapp exec -n "$BE_APP" -g "$RG" --command \
        "python -c \"import urllib.request as u; print('DS /docs →', u.urlopen('https://$ds_fqdn/docs', timeout=20).status)\"" \
        || warn "exec check failed — if CERTIFICATE_VERIFY_FAILED, see fallback in deploy plan"

    info "3. Auth round-trip (placeholder auth)"
    local token
    token=$(curl -fsS -X POST "https://$be_fqdn/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d '{"username":"qa-verify","password":"x"}' | jq -r .access_token)
    [[ -n "$token" && "$token" != "null" ]] && success "login OK" || warn "login failed"

    if [[ -n "$swa_host" ]]; then
        info "4. CORS preflight from SWA origin"
        curl -is -X OPTIONS "https://$be_fqdn/api/auth/login" \
            -H "Origin: https://$swa_host" \
            -H "Access-Control-Request-Method: POST" \
            | grep -i "access-control-allow-origin" \
            && success "CORS OK" || warn "CORS preflight did not echo the SWA origin"
    fi

    header "Deployed URLs"
    echo -e "  Frontend : ${BOLD}https://$swa_host${NC}"
    echo -e "  Backend  : ${BOLD}https://$be_fqdn${NC}"
    echo -e "  DS       : ${BOLD}https://$ds_fqdn${NC} (internal-only)"
    echo ""
    info "Manual checks: open the frontend, log in, run one module generation,"
    info "hard-refresh a deep route (SPA fallback), watch DevTools for CORS errors."
}

# ── Main ──────────────────────────────────────────────────────
case "${1:-all}" in
    all)
        phase_preflight; phase_snapshot; phase_build
        phase_ds_update; phase_ds_internal; phase_backend
        phase_db_verify || true
        phase_swa; phase_cors; phase_frontend; phase_verify
        ;;
    preflight)
        phase_preflight
        ;;
    snapshot|build|ds-update|ds-internal|backend|db-verify|db-apply|swa|cors|frontend|verify)
        phase_preflight
        "phase_${1//-/_}"
        ;;
    *)
        error "Unknown phase: $1"
        echo "Phases: all preflight snapshot build ds-update ds-internal backend db-verify db-apply swa cors frontend verify"
        exit 1
        ;;
esac
