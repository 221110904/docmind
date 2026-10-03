output "sql_server_name" {
  description = "Name of the SQL server"
  value       = azurerm_mssql_server.main.name
}

output "sql_server_fqdn" {
  description = "Fully qualified domain name of the SQL server (used in connection strings)"
  value       = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "Name of the database"
  value       = azurerm_mssql_database.main.name
}

output "sql_admin_username" {
  description = "Admin username for the SQL server"
  value       = var.sql_admin_username
}

output "sql_admin_password" {
  description = "Admin password for the SQL server (sensitive — retrieve with `terraform output -raw sql_admin_password`)"
  value       = random_password.sql_admin.result
  sensitive   = true
}

output "sql_connection_string" {
  description = "ADO-style connection string for the backend app (sensitive)"
  value       = "Server=tcp:${azurerm_mssql_server.main.fully_qualified_domain_name},1433;Database=${azurerm_mssql_database.main.name};User ID=${var.sql_admin_username};Password=${random_password.sql_admin.result};Encrypt=true;Connection Timeout=30;"
  sensitive   = true
}
