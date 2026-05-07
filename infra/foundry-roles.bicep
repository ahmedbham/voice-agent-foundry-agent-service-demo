@description('Existing Foundry (AI Services) account name in this resource group.')
param foundryResourceName string

@description('User/principal running azd; granted Azure AI User on the Foundry account.')
param principalId string

@description('Voice Live system-assigned identity principal id; granted Azure AI User on the Foundry account for cross-resource agent invocation.')
param voiceLiveIdentityPrincipalId string

// Built-in role definition IDs
// Azure AI User: 53ca6127-db72-4b80-b1b0-d745d6d5456d
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource foundry 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: foundryResourceName
}

resource userAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, principalId, azureAiUserRoleId)
  scope: foundry
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
  }
}

resource voiceLiveAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, voiceLiveIdentityPrincipalId, azureAiUserRoleId)
  scope: foundry
  properties: {
    principalId: voiceLiveIdentityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUserRoleId)
  }
}
