targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment.')
param environmentName string

@description('Location used for azd metadata; resources are not created in a new RG.')
param location string = 'eastus2'

@description('Endpoint of the existing Foundry project to reuse, e.g. https://<resource>.services.ai.azure.com/api/projects/<project>.')
param foundryProjectEndpoint string

@description('Resource group containing the existing Foundry (AI Services) account.')
param foundryResourceGroupName string

@description('Resource name of the existing Foundry (AI Services / Cognitive Services) account hosting the project. Used both as the Foundry override and as the Voice Live endpoint host.')
param foundryResourceName string

@description('Project name (last segment of the Foundry project endpoint).')
param foundryProjectName string

@description('Model deployment name on the existing Foundry project to use as the agent model.')
param modelDeploymentName string = 'gpt-4.1-mini'

@description('Name of the Foundry agent that the demo will create / connect to.')
param agentName string = 'MyVoiceAgent'

@description('Object ID of the user/principal running azd up; assigned RBAC on the Foundry account when assignRoles=true.')
param principalId string

@description('When true, create role assignments on the Foundry account. Default false to avoid duplicate-assignment errors when the principal already has the required roles.')
param assignRoles bool = false

module foundryRoleAssignments 'foundry-roles.bicep' = {
  name: 'foundry-roles'
  scope: resourceGroup(foundryResourceGroupName)
  params: {
    foundryResourceName: foundryResourceName
    principalId: principalId
    assignRoles: assignRoles
  }
}

output AZURE_LOCATION string = location
output VOICELIVE_ENDPOINT string = foundryRoleAssignments.outputs.endpoint
output VOICELIVE_API_VERSION string = '2026-01-01-preview'
output PROJECT_ENDPOINT string = foundryProjectEndpoint
output PROJECT_NAME string = foundryProjectName
output FOUNDRY_RESOURCE_OVERRIDE string = foundryResourceName
output MODEL_DEPLOYMENT_NAME string = modelDeploymentName
output AGENT_NAME string = agentName
