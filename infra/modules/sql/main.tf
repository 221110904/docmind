# Random suffix for globally-unique server name (Azure SQL server names must be unique across all of Azure)
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# Random admin password — generated once, stored in Terraform state.
# We never hardcode this in a file, and it's marked sensitive so it won't print in logs.
resource "random_password" "sql_admin" {
  length  = 20
  special = true
  # Avoid characters that cause issues in connection strings / shell quoting
  override_special = "!#$%&*()-_=+"
}

resource "azurerm_mssql_server" "main" {
  name                         = "${var.project_name}-sql-${random_string.suffix.result}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_username
  administrator_login_password = random_password.sql_admin.result

  # TLS 1.2 minimum — required for secure connections
  minimum_tls_version = "1.2"

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# The actual database. "Basic" tier is intentionally cheap (~$5/month) — plenty for dev/demo scale.
resource "azurerm_mssql_database" "main" {
  name           = "${var.project_name}db"
  server_id      = azurerm_mssql_server.main.id
  sku_name       = "Basic"
  max_size_gb    = 2
  zone_redundant = false

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Allow Azure services (App Service, Functions, AKS pods using Azure networking, etc.) to reach this DB.
# This is a special rule Azure recognizes — start/end IP of 0.0.0.0 means "any Azure-internal service."
resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Optional: allow YOUR current machine to connect directly (for local development / running migrations by hand).
# Only created if you pass in your IP via allowed_client_ip.
resource "azurerm_mssql_firewall_rule" "allow_dev_machine" {
  count            = var.allowed_client_ip != "" ? 1 : 0
  name             = "AllowDevMachine"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = var.allowed_client_ip
  end_ip_address   = var.allowed_client_ip
}
