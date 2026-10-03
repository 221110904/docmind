output "openai_endpoint" {
  value = azurerm_cognitive_account.main.endpoint
}

output "openai_primary_key" {
  value     = azurerm_cognitive_account.main.primary_access_key
  sensitive = true
}

output "gpt4o_deployment_name" {
  value = azurerm_cognitive_deployment.gpt4o.name
}

output "embeddings_deployment_name" {
  value = azurerm_cognitive_deployment.embeddings.name
}