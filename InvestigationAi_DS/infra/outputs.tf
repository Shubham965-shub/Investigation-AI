output "app_fqdn" {
  description = "HTTPS FQDN of the deployed Container App"
  value       = "https://${azurerm_container_app.search_agent.ingress[0].fqdn}"
}

output "acr_login_server" {
  description = "Login server of the existing ACR"
  value       = data.azurerm_container_registry.acr.login_server
}

output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.main.name
}

output "container_app_name" {
  description = "Container App name"
  value       = azurerm_container_app.search_agent.name
}
