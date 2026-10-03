output "storage_account_name" {
  description = "Name of the storage account holding uploaded documents"
  value       = azurerm_storage_account.documents.name
}

output "storage_account_primary_connection_string" {
  description = "Connection string for the storage account (used by the backend app and Azure Functions)"
  value       = azurerm_storage_account.documents.primary_connection_string
  sensitive   = true
}

output "documents_container_name" {
  description = "Name of the blob container that holds uploaded documents"
  value       = azurerm_storage_container.documents.name
}

output "storage_account_id" {
  description = "Resource ID of the storage account"
  value       = azurerm_storage_account.documents.id
}
