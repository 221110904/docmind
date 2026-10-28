# Cloud hosting for DocMind: a container registry, the backend as a Container App that
# scales to zero, logs in Log Analytics, and the frontend on a free Static Web App.
# Everything here is created only when enable_hosting = true.

resource "random_string" "hosting_suffix" {
  count   = var.enable_hosting ? 1 : 0
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_log_analytics_workspace" "main" {
  count               = var.enable_hosting ? 1 : 0
  name                = "${var.project_name}-logs"
  location            = var.app_location
  resource_group_name = data.azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 0.5 # a hard cap, so logging can never run up a bill

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_container_registry" "main" {
  count               = var.enable_hosting ? 1 : 0
  name                = "${var.project_name}acr${random_string.hosting_suffix[0].result}"
  location            = var.app_location
  resource_group_name = data.azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = true # the Container App pulls images with this account

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_container_app_environment" "main" {
  count                      = var.enable_hosting ? 1 : 0
  name                       = "${var.project_name}-env"
  location                   = var.app_location
  resource_group_name        = data.azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main[0].id

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_static_web_app" "frontend" {
  count               = var.enable_hosting ? 1 : 0
  name                = "${var.project_name}-web"
  location            = var.app_location
  resource_group_name = data.azurerm_resource_group.main.name
  sku_tier            = "Free"
  sku_size            = "Free"

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

locals {
  database_url = var.enable_hosting ? try(join("", [
    "mssql+pyodbc://",
    module.sql[0].sql_admin_username,
    ":",
    urlencode(module.sql[0].sql_admin_password),
    "@",
    module.sql[0].sql_server_fqdn,
    ":1433/",
    module.sql[0].sql_database_name,
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&LoginTimeout=30",
  ]), "") : ""
}

resource "azurerm_container_app" "backend" {
  count                        = var.enable_hosting ? 1 : 0
  name                         = "${var.project_name}-api"
  container_app_environment_id = azurerm_container_app_environment.main[0].id
  resource_group_name          = data.azurerm_resource_group.main.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.main[0].login_server
    username             = azurerm_container_registry.main[0].admin_username
    password_secret_name = "registry-password"
  }

  secret {
    name  = "registry-password"
    value = azurerm_container_registry.main[0].admin_password
  }

  secret {
    name  = "database-url"
    value = local.database_url
  }

  secret {
    name  = "storage-connection"
    value = module.storage.storage_account_primary_connection_string
  }

  secret {
    name  = "openai-key"
    value = module.openai.openai_primary_key
  }

  secret {
    name  = "search-key"
    value = module.search.search_primary_admin_key
  }

  secret {
    name  = "docintel-key"
    value = coalesce(one(module.documentintelligence[*].primary_key), "none")
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.backend_min_replicas
    max_replicas = 2

    # The image is a placeholder until the first deployment pushes the real one. The
    # deploy workflow changes the image, so Terraform ignores it (see lifecycle below).
    container {
      name   = "api"
      image  = "mcr.microsoft.com/k8se/quickstart:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "STORAGE_BACKEND"
        value = "azure"
      }
      env {
        name        = "AZURE_STORAGE_CONNECTION_STRING"
        secret_name = "storage-connection"
      }
      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = module.storage.documents_container_name
      }
      env {
        name  = "OCR_BACKEND"
        value = var.enable_document_intelligence ? "azure" : "none"
      }
      env {
        name  = "DOCUMENT_INTELLIGENCE_ENDPOINT"
        value = coalesce(one(module.documentintelligence[*].endpoint), "none")
      }
      env {
        name        = "DOCUMENT_INTELLIGENCE_KEY"
        secret_name = "docintel-key"
      }
      env {
        name  = "EMBEDDING_BACKEND"
        value = "azure"
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = module.openai.openai_endpoint
      }
      env {
        name        = "AZURE_OPENAI_KEY"
        secret_name = "openai-key"
      }
      env {
        name  = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
        value = module.openai.embeddings_deployment_name
      }
      env {
        name  = "AZURE_OPENAI_CHAT_DEPLOYMENT"
        value = module.openai.gpt4o_deployment_name
      }
      env {
        name  = "QA_BACKEND"
        value = "azure"
      }
      env {
        name  = "SEARCH_BACKEND"
        value = "azure"
      }
      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = module.search.search_service_endpoint
      }
      env {
        name        = "AZURE_SEARCH_KEY"
        secret_name = "search-key"
      }
      env {
        name  = "AUTH_BACKEND"
        value = "entra"
      }
      env {
        name  = "ENTRA_TENANT_ID"
        value = var.entra_tenant_id
      }
      env {
        name  = "ENTRA_TENANT_SUBDOMAIN"
        value = var.entra_tenant_subdomain
      }
      env {
        name  = "ENTRA_API_CLIENT_ID"
        value = var.entra_api_client_id
      }
      env {
        name  = "CORS_ORIGINS"
        value = "https://${azurerm_static_web_app.frontend[0].default_host_name}"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]

    precondition {
      condition     = local.database_url != ""
      error_message = "Hosting needs the database. Run again with -var enable_sql=true as well."
    }
  }

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

output "container_registry_name" {
  value = one(azurerm_container_registry.main[*].name)
}

output "backend_url" {
  value = var.enable_hosting ? "https://${azurerm_container_app.backend[0].ingress[0].fqdn}" : null
}

output "frontend_url" {
  value = var.enable_hosting ? "https://${azurerm_static_web_app.frontend[0].default_host_name}" : null
}

output "frontend_deploy_token" {
  value     = one(azurerm_static_web_app.frontend[*].api_key)
  sensitive = true
}
