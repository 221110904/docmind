resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# Serverless capacity mode = pay only for what you use (no fixed hourly cost)
resource "azurerm_cosmosdb_account" "main" {
  name                = "${var.project_name}-cosmos-${random_string.suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB" # Core (SQL) API

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "${var.project_name}db"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "workspaces" {
  name                = "workspaces"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/workspaceId"]
}

resource "azurerm_cosmosdb_sql_container" "ingestion_log" {
  name                = "ingestion_log"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/workspaceId"]
}