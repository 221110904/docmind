variable "enable_hosting" {
  description = "Create the cloud hosting (container registry, backend app, frontend site). Parked (false) by default to avoid charges. Needs enable_sql = true."
  type        = bool
  default     = false
}

variable "app_location" {
  description = "Azure region for the hosting resources. Static Web Apps only exist in a few regions (centralus is one), so everything is kept together there."
  type        = string
  default     = "centralus"
}

variable "backend_min_replicas" {
  description = "0 lets the backend scale to zero when idle (cheapest, but the first request after a pause is slow). Use 1 on demo day."
  type        = number
  default     = 0
}

variable "entra_tenant_id" {
  description = "Directory (tenant) ID of the External ID tenant used for sign-in"
  type        = string
  default     = "3f5f8e17-f7c3-4938-8fae-5f081b76f39f"
}

variable "entra_tenant_subdomain" {
  description = "Subdomain of the External ID tenant (docmindauth for docmindauth.ciamlogin.com)"
  type        = string
  default     = "docmindauth"
}

variable "entra_api_client_id" {
  description = "Application (client) ID of the DocMind API registration"
  type        = string
  default     = "843c3324-8ed5-4039-8a83-bc1a1e22cf3b"
}
