# Week 1 scope: reference the resource group you already created via Azure CLI.
# Week 2 will add modules for AKS, Storage, Cosmos DB, AI Search, OpenAI, etc.
# by uncommenting/adding module blocks below, e.g.:
#
# module "storage" {
#   source              = "../../modules/storage"
#   resource_group_name = var.resource_group_name
#   location            = var.location
#   project_name        = var.project_name
# }

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

output "resource_group_id" {
  value = data.azurerm_resource_group.main.id
}

output "resource_group_location" {
  value = data.azurerm_resource_group.main.location
}
