variable "resource_group_name" {
  description = "Resource group to deploy into"
  type        = string
}

variable "location" {
  description = "Azure region for the SQL server (some regions restrict SQL provisioning for new free-trial subscriptions)"
  type        = string
}

variable "project_name" {
  description = "Short project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "sql_admin_username" {
  description = "Admin username for the SQL server"
  type        = string
  default     = "docmindadmin"
}

variable "allowed_client_ip" {
  description = "Your current public IP address, so you can connect to the DB directly for development/debugging. Leave empty to skip this rule."
  type        = string
  default     = ""
}
