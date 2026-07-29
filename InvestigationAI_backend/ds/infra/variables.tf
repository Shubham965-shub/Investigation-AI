# ── General ───────────────────────────────────────────────────
variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to create for Container Apps"
  type        = string
  default     = "rg-investigationai-ds"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "centralindia"
}

# ── Existing ACR ──────────────────────────────────────────────
variable "acr_name" {
  description = "Name of the existing Azure Container Registry"
  type        = string
}

variable "acr_resource_group_name" {
  description = "Resource group where the existing ACR resides"
  type        = string
}

# ── Container App ─────────────────────────────────────────────
variable "container_app_name" {
  description = "Name of the Container App"
  type        = string
  default     = "investigationai-search-agent"
}

variable "container_app_env_name" {
  description = "Name of the Container Apps Environment"
  type        = string
  default     = "investigationai-ds-env"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "cpu" {
  description = "CPU cores allocated to the container"
  type        = number
  default     = 0.5
}

variable "memory" {
  description = "Memory allocated to the container (e.g. 1Gi)"
  type        = string
  default     = "1Gi"
}

variable "min_replicas" {
  description = "Minimum number of replicas"
  type        = number
  default     = 0
}

variable "max_replicas" {
  description = "Maximum number of replicas"
  type        = number
  default     = 3
}

# ── Secrets (from .env) ──────────────────────────────────────
variable "db_host" {
  description = "PostgreSQL host"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  sensitive   = true
}

variable "db_user" {
  description = "PostgreSQL user"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "db_port" {
  description = "PostgreSQL port"
  type        = string
  default     = "5432"
}

variable "db_pool_min_size" {
  description = "Minimum DB connection pool size"
  type        = string
  default     = "1"
}

variable "db_pool_max_size" {
  description = "Maximum DB connection pool size"
  type        = string
  default     = "20"
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}
