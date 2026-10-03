terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state backend — points at the storage account you created via Azure CLI.
  # Fill in the values below (or pass them via `terraform init -backend-config=...`)
  backend "azurerm" {
    resource_group_name = "docmind-rg"
    storage_account_name = "docmindtfstate45344"
    container_name       = "tfstate"
    key                  = "dev.terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}
