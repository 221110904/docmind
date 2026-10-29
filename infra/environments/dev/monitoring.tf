# Alerts and a spending budget. Created only when alert_email is set.

resource "azurerm_monitor_action_group" "email" {
  count               = var.alert_email != "" ? 1 : 0
  name                = "${var.project_name}-alerts"
  resource_group_name = data.azurerm_resource_group.main.name
  short_name          = "docmind"

  email_receiver {
    name          = "owner"
    email_address = var.alert_email
  }
}

# More than 5 server errors (HTTP 5xx) in 5 minutes
resource "azurerm_monitor_metric_alert" "backend_errors" {
  count               = var.enable_hosting && var.alert_email != "" ? 1 : 0
  name                = "${var.project_name}-backend-errors"
  resource_group_name = data.azurerm_resource_group.main.name
  scopes              = [azurerm_container_app.backend[0].id]
  description         = "The backend returned more than 5 server errors in 5 minutes"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 5

    dimension {
      name     = "statusCodeCategory"
      operator = "Include"
      values   = ["5xx"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.email[0].id
  }
}

# The container restarting repeatedly means it is crashing
resource "azurerm_monitor_metric_alert" "backend_restarts" {
  count               = var.enable_hosting && var.alert_email != "" ? 1 : 0
  name                = "${var.project_name}-backend-restarts"
  resource_group_name = data.azurerm_resource_group.main.name
  scopes              = [azurerm_container_app.backend[0].id]
  description         = "The backend container restarted more than 3 times in 15 minutes"
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "RestartCount"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = azurerm_monitor_action_group.email[0].id
  }
}

resource "azurerm_consumption_budget_resource_group" "main" {
  count             = var.alert_email != "" ? 1 : 0
  name              = "${var.project_name}-monthly"
  resource_group_id = data.azurerm_resource_group.main.id
  amount            = var.monthly_budget_usd
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = [50, 80, 100]

    content {
      enabled        = true
      threshold      = notification.value
      operator       = "GreaterThan"
      threshold_type = "Actual"
      contact_emails = [var.alert_email]
    }
  }
}
