resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# Azure AI Search service — the unified vector + keyword search engine.
# IMPORTANT: Free tier cannot be upgraded to a paid tier in place. Switching later means
# creating a new service at the desired tier and re-running the ingestion pipeline to re-index.
# You get exactly ONE free-tier search service per subscription.
resource "azurerm_search_service" "main" {
  name                = "${var.project_name}-search-${random_string.suffix.result}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku

  replica_count   = 1
  partition_count = 1

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}