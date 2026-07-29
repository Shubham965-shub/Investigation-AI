#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  deploy.sh — Interactive deployment script for InvestigationAI
#              Search Agent on Azure Container Apps
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/infra"
IMAGE_NAME="investigationai-search-agent"

# ── Helper functions ──────────────────────────────────────────
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

# ── Prerequisite checks ──────────────────────────────────────
check_prerequisites() {
    header "Checking prerequisites"
    local missing=0

    for cmd in az terraform docker; do
        if command -v "$cmd" &>/dev/null; then
            success "$cmd found: $(command -v "$cmd")"
        else
            error "$cmd is not installed"
            missing=1
        fi
    done

    if [[ $missing -eq 1 ]]; then
        error "Please install missing prerequisites and try again."
        exit 1
    fi

    # Check Azure login
    if az account show &>/dev/null; then
        local account_name
        account_name=$(az account show --query name -o tsv 2>/dev/null)
        success "Azure CLI logged in: ${account_name}"
    else
        warn "Not logged into Azure CLI."
        if confirm "Log in now?"; then
            az login
            success "Azure login successful."
        else
            error "Azure login required. Exiting."
            exit 1
        fi
    fi

    echo ""
    success "All prerequisites met."
}

# ── Terraform: init + apply ───────────────────────────────────
terraform_apply() {
    header "Terraform — Provision Infrastructure"

    if [[ ! -f "${INFRA_DIR}/terraform.tfvars" ]]; then
        warn "No terraform.tfvars found in ${INFRA_DIR}/"
        info "Copy terraform.tfvars.example to terraform.tfvars and fill in your values:"
        echo -e "  ${BOLD}cp ${INFRA_DIR}/terraform.tfvars.example ${INFRA_DIR}/terraform.tfvars${NC}"
        echo ""
        if ! confirm "Have you created and configured terraform.tfvars?"; then
            error "Please create terraform.tfvars first. Exiting."
            exit 1
        fi
    fi

    info "Initializing Terraform..."
    terraform -chdir="${INFRA_DIR}" init

    echo ""
    info "Planning changes..."
    terraform -chdir="${INFRA_DIR}" plan -out=tfplan

    echo ""
    if confirm "Apply the plan above?"; then
        terraform -chdir="${INFRA_DIR}" apply tfplan
        rm -f "${INFRA_DIR}/tfplan"
        success "Infrastructure provisioned."
    else
        rm -f "${INFRA_DIR}/tfplan"
        warn "Terraform apply skipped."
    fi
}

# ── Docker: build + tag + push ────────────────────────────────
docker_build_push() {
    header "Docker — Build & Push Image"

    local acr_server image_tag

    # Read ACR server from Terraform output
    acr_server=$(terraform -chdir="${INFRA_DIR}" output -raw acr_login_server 2>/dev/null || true)
    if [[ -z "$acr_server" ]]; then
        echo -en "${YELLOW}Enter ACR login server (e.g. myacr.azurecr.io): ${NC}"
        read -r acr_server
    else
        info "ACR login server: ${acr_server}"
    fi

    echo -en "${YELLOW}Enter image tag [latest]: ${NC}"
    read -r image_tag
    image_tag="${image_tag:-latest}"

    local full_image="${acr_server}/${IMAGE_NAME}:${image_tag}"

    info "Logging in to ACR: ${acr_server}..."
    az acr login --name "${acr_server%%.*}"

    info "Building Docker image..."
    docker build -t "${IMAGE_NAME}:${image_tag}" "${SCRIPT_DIR}"

    info "Tagging image as ${full_image}..."
    docker tag "${IMAGE_NAME}:${image_tag}" "${full_image}"

    if confirm "Push ${full_image} to ACR?"; then
        docker push "${full_image}"
        success "Image pushed: ${full_image}"
    else
        warn "Push skipped."
    fi
}

# ── Update Container App ──────────────────────────────────────
update_app() {
    header "Update Container App"

    local rg_name app_name acr_server image_tag

    rg_name=$(terraform -chdir="${INFRA_DIR}" output -raw resource_group_name 2>/dev/null || true)
    app_name=$(terraform -chdir="${INFRA_DIR}" output -raw container_app_name 2>/dev/null || true)
    acr_server=$(terraform -chdir="${INFRA_DIR}" output -raw acr_login_server 2>/dev/null || true)

    if [[ -z "$rg_name" ]]; then
        echo -en "${YELLOW}Enter resource group name: ${NC}"
        read -r rg_name
    fi
    if [[ -z "$app_name" ]]; then
        echo -en "${YELLOW}Enter container app name: ${NC}"
        read -r app_name
    fi
    if [[ -z "$acr_server" ]]; then
        echo -en "${YELLOW}Enter ACR login server: ${NC}"
        read -r acr_server
    fi

    echo -en "${YELLOW}Enter image tag to deploy [latest]: ${NC}"
    read -r image_tag
    image_tag="${image_tag:-latest}"

    local full_image="${acr_server}/${IMAGE_NAME}:${image_tag}"

    info "Updating ${app_name} → ${full_image}..."
    az containerapp update \
        --name "$app_name" \
        --resource-group "$rg_name" \
        --image "$full_image"

    success "Container App updated."

    # Print FQDN
    local fqdn
    fqdn=$(az containerapp show \
        --name "$app_name" \
        --resource-group "$rg_name" \
        --query "properties.configuration.ingress.fqdn" \
        -o tsv 2>/dev/null || true)

    if [[ -n "$fqdn" ]]; then
        echo ""
        success "App is live at: ${BOLD}https://${fqdn}${NC}"
    fi
}

# ── Destroy ───────────────────────────────────────────────────
destroy() {
    header "Destroy Infrastructure"

    warn "This will destroy ALL resources managed by Terraform."
    echo ""
    if confirm "Are you sure you want to destroy everything?"; then
        terraform -chdir="${INFRA_DIR}" destroy
        success "Infrastructure destroyed."
    else
        info "Destroy cancelled."
    fi
}

# ── Full deploy ───────────────────────────────────────────────
full_deploy() {
    terraform_apply
    docker_build_push
    update_app

    header "Deployment Complete"

    local fqdn
    fqdn=$(terraform -chdir="${INFRA_DIR}" output -raw app_fqdn 2>/dev/null || true)
    if [[ -n "$fqdn" ]]; then
        success "App is live at: ${BOLD}${fqdn}${NC}"
    fi
}

# ── Interactive menu ──────────────────────────────────────────
show_menu() {
    echo ""
    echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║   InvestigationAI Search Agent — Deployer     ║${NC}"
    echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}1)${NC} 🚀 Full deploy  (infra → build → deploy)"
    echo -e "  ${BOLD}2)${NC} 🏗️  Infra only   (Terraform init + apply)"
    echo -e "  ${BOLD}3)${NC} 🐳 Build & push (Docker build + push to ACR)"
    echo -e "  ${BOLD}4)${NC} 🔄 Update app   (Update Container App image)"
    echo -e "  ${BOLD}5)${NC} 💥 Destroy      (Tear down all infrastructure)"
    echo -e "  ${BOLD}6)${NC} ❌ Exit"
    echo ""
    echo -en "${YELLOW}Select an option [1-6]: ${NC}"
}

# ── Main ──────────────────────────────────────────────────────
main() {
    check_prerequisites

    while true; do
        show_menu
        read -r choice
        case "$choice" in
            1) full_deploy ;;
            2) terraform_apply ;;
            3) docker_build_push ;;
            4) update_app ;;
            5) destroy ;;
            6) info "Goodbye!"; exit 0 ;;
            *) warn "Invalid option. Please select 1-6." ;;
        esac
    done
}

main "$@"
