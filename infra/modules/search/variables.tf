variable "resource_group_name" {
  description = "Resource group to deploy into"
  type        = string
}

variable "location" {
  description = "Azure region for the search service"
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

variable "sku" {
  description = "Pricing tier: free (default, $0, no semantic ranking) or basic/standard (paid, supports semantic ranking). NOTE: Free tier cannot be upgraded in place — switching to a paid tier later requires creating a new service and re-indexing."
  type        = string
  default     = "free"
}