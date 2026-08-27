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
