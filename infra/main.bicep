targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment; used to namespace resources.')
param environmentName string

@description('Location for the Voice Live (AI Services) resource. Must be a supported Voice Live region.')
@allowed([
  'eastus2'
  'swedencentral'
  'westus2'
  'southeastasia'
])
param voiceLiveLocation string = 'eastus2'

@description('Resource group name for the Voice Live resource. Defaults to rg-<env>.')
param resourceGroupName string = ''

@description('Endpoint of the existing Foundry project to reuse, e.g. https://<resource>.services.ai.azure.com/api/projects/<project>.')
param foundryProjectEndpoint string

@description('Resource group containing the existing Foundry project.')
param foundryResourceGroupName string

@description('Resource name of the existing Foundry (AI Services / Cognitive Services) account hosting the project.')
param foundryResourceName string

@description('Project name (last segment of the Foundry project endpoint).')
param foundryProjectName string

@description('Model deployment name on the existing Foundry project to use as the agent model.')
param modelDeploymentName string = 'gpt-4.1-mini'

@description('Name of the Foundry agent that the demo will create / connect to.')
param agentName string = 'MyVoiceAgent'

@description('Object ID of the user/principal running azd up; assigned RBAC on the Voice Live and Foundry resources.')
param principalId string

var rgName = empty(resourceGroupName) ? 'rg-${environmentName}' : resourceGroupName
var voiceLiveAccountName = take('voicelive-${uniqueString(subscription().id, environmentName)}', 24)

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: voiceLiveLocation
  tags: {
    'azd-env-name': environmentName
  }
}

module voiceLive 'voicelive.bicep' = {
  name: 'voicelive'
  scope: rg
  params: {
    name: voiceLiveAccountName
    location: voiceLiveLocation
    tags: {
      'azd-env-name': environmentName
    }
  }
}

module foundryRoleAssignments 'foundry-roles.bicep' = {
  name: 'foundry-roles'
  scope: resourceGroup(foundryResourceGroupName)
  params: {
    foundryResourceName: foundryResourceName
    principalId: principalId
    voiceLiveIdentityPrincipalId: voiceLive.outputs.principalId
  }
}

output AZURE_LOCATION string = voiceLiveLocation
output AZURE_RESOURCE_GROUP string = rg.name
output VOICELIVE_ENDPOINT string = voiceLive.outputs.endpoint
output VOICELIVE_API_VERSION string = '2026-01-01-preview'
output PROJECT_ENDPOINT string = foundryProjectEndpoint
output PROJECT_NAME string = foundryProjectName
output FOUNDRY_RESOURCE_OVERRIDE string = foundryResourceName
output MODEL_DEPLOYMENT_NAME string = modelDeploymentName
output AGENT_NAME string = agentName
