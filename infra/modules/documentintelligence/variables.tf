variable "resource_group_name" {
  description = "Resource group to deploy into"
  type        = string
}

variable "location" {
  description = "Azure region for Document Intelligence"
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
  description = "Pricing tier: F0 is free (500 pages per month, 2 pages per request, 4 MB files); S0 is paid"
  type        = string
  default     = "F0"
}
