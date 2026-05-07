@description('Existing Foundry (AI Services / Cognitive Services) account name. Its endpoint is used as VOICELIVE_ENDPOINT.')
param foundryResourceName string

@description('User/principal running azd; granted Azure AI User on the Foundry account when assignRoles=true.')
param principalId string

@description('When true, create the Azure AI User and Cognitive Services User role assignments on the Foundry account. Set to false if the principal already has these roles (avoids duplicate-assignment errors).')
param assignRoles bool = false

// Built-in role definition IDs
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Azure AI User
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: foundryResourceName
}

resource userAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignRoles) {
  name: guid(foundry.id, principalId, azureAiUserRoleId)
  scope: foundry
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
  }
}

resource userCognitiveServicesUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignRoles) {
  name: guid(foundry.id, principalId, cognitiveServicesUserRoleId)
  scope: foundry
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
  }
}

output endpoint string = foundry.properties.endpoint
