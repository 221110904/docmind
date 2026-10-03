output "search_service_name" {
  value = azurerm_search_service.main.name
}

output "search_service_endpoint" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "search_primary_admin_key" {
  value     = azurerm_search_service.main.primary_key
  sensitive = true
}