# ── Log Analytics Workspace ───────────────────────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.container_app_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = azurerm_resource_group.main.tags
}

# ── Container Apps Environment ────────────────────────────────
resource "azurerm_container_app_environment" "main" {
  name                       = var.container_app_env_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = azurerm_resource_group.main.tags
}

# ── Container App ─────────────────────────────────────────────
resource "azurerm_container_app" "search_agent" {
  name                         = var.container_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  tags = azurerm_resource_group.main.tags

  # ── Registry authentication (existing ACR) ──────────────────
  registry {
    server               = data.azurerm_container_registry.acr.login_server
    username             = data.azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  # ── Secrets ─────────────────────────────────────────────────
  secret {
    name  = "acr-password"
    value = data.azurerm_container_registry.acr.admin_password
  }

  secret {
    name  = "db-host"
    value = var.db_host
  }

  secret {
    name  = "db-name"
    value = var.db_name
  }

  secret {
    name  = "db-user"
    value = var.db_user
  }

  secret {
    name  = "db-password"
    value = var.db_password
  }

  secret {
    name  = "db-port"
    value = var.db_port
  }

  secret {
    name  = "db-pool-min-size"
    value = var.db_pool_min_size
  }

  secret {
    name  = "db-pool-max-size"
    value = var.db_pool_max_size
  }

  secret {
    name  = "openai-api-key"
    value = var.openai_api_key
  }

  # ── Ingress (HTTPS) ────────────────────────────────────────
  ingress {
    external_enabled = true
    target_port      = 8001
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  # ── Container template ─────────────────────────────────────
  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "search-agent"
      image  = "${data.azurerm_container_registry.acr.login_server}/${var.container_app_name}:${var.image_tag}"
      cpu    = var.cpu
      memory = var.memory

      # ── Environment variables (referencing secrets) ─────────
      env {
        name        = "DB_HOST"
        secret_name = "db-host"
      }

      env {
        name        = "DB_NAME"
        secret_name = "db-name"
      }

      env {
        name        = "DB_USER"
        secret_name = "db-user"
      }

      env {
        name        = "DB_PASSWORD"
        secret_name = "db-password"
      }

      env {
        name        = "DB_PORT"
        secret_name = "db-port"
      }

      env {
        name        = "DB_POOL_MIN_SIZE"
        secret_name = "db-pool-min-size"
      }

      env {
        name        = "DB_POOL_MAX_SIZE"
        secret_name = "db-pool-max-size"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }

      env {
        name  = "SEARCH_AGENT_HOST"
        value = "0.0.0.0"
      }

      env {
        name  = "SEARCH_AGENT_PORT"
        value = "8001"
      }
    }
  }
}
