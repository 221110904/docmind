variable "alert_email" {
  description = "Email address that receives failure alerts and budget warnings. Leave empty to skip monitoring alerts and the budget."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly spending limit for the resource group, in US dollars. Warnings are emailed at 50%, 80% and 100%."
  type        = number
  default     = 30
}

variable "budget_start_date" {
  description = "First day of the month the budget starts counting from (must be the 1st of a month)."
  type        = string
  default     = "2026-10-01T00:00:00Z"
}
