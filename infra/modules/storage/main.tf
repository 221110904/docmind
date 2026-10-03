# Random suffix so the storage account name is globally unique
# (Azure requires storage account names to be unique across ALL of Azure, not just your subscription)
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_storage_account" "documents" {
  # Storage account names: lowercase letters/numbers only, 3-24 chars, must be globally unique
  name                     = "${var.project_name}doc${random_string.suffix.result}"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS" # Locally redundant — cheapest option, fine for a dev/demo project
  allow_nested_items_to_be_public = false

  # Blob versioning helps if you accidentally overwrite/delete an uploaded document
  blob_properties {
    versioning_enabled = true
  }

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Container that holds the raw uploaded documents (PDFs, images, DOCX, etc.)
resource "azurerm_storage_container" "documents" {
  name                  = "documents"
  storage_account_name  = azurerm_storage_account.documents.name
  container_access_type = "private"
}