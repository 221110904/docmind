variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Name of the resource group all resources live in"
  type        = string
  default     = "docmind-rg"
}

variable "project_name" {
  description = "Short project name used as a prefix for resource naming"
  type        = string
  default     = "docmind"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "sql_location" {
  description = "Azure region for the SQL server. Some regions (like eastus) block SQL provisioning for new free-trial subscriptions."
  type        = string
  default     = "centralus"
}

variable "my_ip_address" {
  description = "Your current public IP address, so you can connect to the SQL database directly (e.g. via SSMS or Azure Data Studio). Leave blank to skip. Find yours at https://whatismyipaddress.com"
  type        = string
  default     = ""
}
