output "endpoint" {
  description = "Endpoint URL of the Document Intelligence resource"
  value       = azurerm_cognitive_account.main.endpoint
}

output "primary_key" {
  description = "Primary API key (sensitive)"
  value       = azurerm_cognitive_account.main.primary_access_key
  sensitive   = true
}
