resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_cognitive_account" "main" {
  name                  = "${var.project_name}-openai-${random_string.suffix.result}"
  resource_group_name   = var.resource_group_name
  location              = var.location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "${var.project_name}-openai-${random_string.suffix.result}"

  tags = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "azurerm_cognitive_deployment" "gpt4o" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.main.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-11-20"
  }

  scale {
    type     = "Standard"
    capacity = var.gpt4o_capacity
  }
}

resource "azurerm_cognitive_deployment" "embeddings" {
  name                 = "text-embedding-3-large"
  cognitive_account_id = azurerm_cognitive_account.main.id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-large"
    version = "1"
  }

  scale {
    type     = "Standard"
    capacity = var.embedding_capacity
  }
}