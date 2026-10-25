resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# Azure AI Document Intelligence (the Azure provider still calls it "FormRecognizer").
# F0 is free but limited: 500 pages per month, only the first 2 pages of a document
# per request, and files up to 4 MB. The backend sends scans in small batches for this reason.
resource "azurerm_cognitive_account" "main" {
  name                  = "${var.project_name}-docintel-${random_string.suffix.result}"
  resource_group_name   = var.resource_group_name
  location              = var.location
  kind                  = "FormRecognizer"
  sku_name              = var.sku
  custom_subdomain_name = "${var.project_name}-docintel-${random_string.suffix.result}"

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}
