data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

# Week 2: Blob Storage for uploaded documents
module "storage" {
  source = "../../modules/storage"

  resource_group_name = data.azurerm_resource_group.main.name
  location             = data.azurerm_resource_group.main.location
  project_name         = var.project_name
  environment          = var.environment
}

# Week 2: Azure SQL Database for users/roles
module "sql" {
  source = "../../modules/sql"

  resource_group_name = data.azurerm_resource_group.main.name
  location             = var.sql_location
  project_name         = var.project_name
  environment          = var.environment
  allowed_client_ip    = var.my_ip_address
}


# Week 2: Cosmos DB for workspace metadata + ingestion status
module "cosmosdb" {
  source = "../../modules/cosmosdb"

  resource_group_name = data.azurerm_resource_group.main.name
  location             = var.sql_location
  project_name         = var.project_name
  environment          = var.environment
}


# Week 2: Azure AI Search (Free tier — hybrid keyword + vector search, no semantic ranking)
module "search" {
  source = "../../modules/search"

  resource_group_name = data.azurerm_resource_group.main.name
  location             = var.location # eastus — free tier default
  project_name         = var.project_name
  environment          = var.environment
  sku                  = "free"
}

output "resource_group_id" {
  value = data.azurerm_resource_group.main.id
}

output "resource_group_location" {
  value = data.azurerm_resource_group.main.location
}

output "storage_account_name" {
  value = module.storage.storage_account_name
}

output "documents_container_name" {
  value = module.storage.documents_container_name
}

output "sql_server_fqdn" {
  value = module.sql.sql_server_fqdn
}

output "sql_database_name" {
  value = module.sql.sql_database_name
}

output "sql_admin_username" {
  value = module.sql.sql_admin_username
}


output "cosmosdb_endpoint" {
  value = module.cosmosdb.cosmosdb_endpoint
}

output "cosmosdb_database_name" {
  value = module.cosmosdb.cosmosdb_database_name
}


output "search_service_endpoint" {
  value = module.search.search_service_endpoint
}
