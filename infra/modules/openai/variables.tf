variable "resource_group_name" {
  description = "Resource group to deploy into"
  type        = string
}

variable "location" {
  description = "Azure region for the OpenAI resource"
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

variable "gpt4o_capacity" {
  description = "Tokens-per-minute capacity for GPT-4o deployment, in thousands"
  type        = number
  default     = 10
}

variable "embedding_capacity" {
  description = "Tokens-per-minute capacity for embeddings deployment, in thousands"
  type        = number
  default     = 10
}