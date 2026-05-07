@description('Voice Live (AI Services) account name.')
param name string

@description('Region for the Voice Live resource.')
param location string

@description('Resource tags.')
param tags object = {}

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

output endpoint string = account.properties.endpoint
output name string = account.name
output principalId string = account.identity.principalId
