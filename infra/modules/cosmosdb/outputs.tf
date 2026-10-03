output "cosmosdb_account_name" {
  value = azurerm_cosmosdb_account.main.name
}

output "cosmosdb_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "cosmosdb_primary_key" {
  value     = azurerm_cosmosdb_account.main.primary_key
  sensitive = true
}

output "cosmosdb_database_name" {
  value = azurerm_cosmosdb_sql_database.main.name
}

output "workspaces_container_name" {
  value = azurerm_cosmosdb_sql_container.workspaces.name
}

output "ingestion_log_container_name" {
  value = azurerm_cosmosdb_sql_container.ingestion_log.name
}