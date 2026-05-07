# Voice Agent with Foundry Agent Service — Demo

End-to-end demo of the [Voice Live + Foundry Agent Service quickstart](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-agents-quickstart?tabs=windows&pivots=programming-language-python), provisioned with `azd`, with an automated WAV-driven E2E test and per-turn latency metrics.

## Prerequisites

- Python 3.10+
- An existing Microsoft Foundry project + model deployment (e.g. `gpt-4.1-mini`)
- Azure CLI (`az`) and Azure Developer CLI (`azd`)
- A microphone + speakers (only for the interactive client)

On Windows, PyAudio sometimes fails to install via pip. Fallback:

```pwsh
pip install pipwin
pipwin install pyaudio
```

## What gets provisioned

`azd up` creates:

- A Voice Live (AI Services) resource in a supported region
- Role assignments:
  - Voice Live resource's managed identity → **Azure AI User** on the existing Foundry project (cross-resource agent invocation)
  - Current user → **Azure AI User** on the existing Foundry project

The existing Foundry project is **reused** — no new Foundry project is created. After provisioning, the post-provision hook installs Python dependencies and creates the agent (`src/create_agent_with_voicelive.py`).

## Setup

1. Sign in:

   ```pwsh
   az login
   azd auth login
   ```

2. Initialize the azd environment and supply Foundry project info:

   ```pwsh
   azd env new voice-agent-demo
   azd env set FOUNDRY_PROJECT_ENDPOINT "https://<resource>.services.ai.azure.com/api/projects/<project>"
   azd env set FOUNDRY_RESOURCE_GROUP   "<rg-of-foundry-resource>"
   azd env set FOUNDRY_RESOURCE_NAME    "<foundry-resource-name>"
   azd env set FOUNDRY_PROJECT_NAME     "<project>"
   azd env set MODEL_DEPLOYMENT_NAME    "gpt-4.1-mini"
   azd env set AGENT_NAME               "MyVoiceAgent"
   azd env set AZURE_LOCATION           "eastus2"
   ```

3. Provision and create the agent:

   ```pwsh
   azd up
   ```

   `azd` writes outputs (including `VOICELIVE_ENDPOINT`, `PROJECT_ENDPOINT`, etc.) into the azd environment. Copy them into a local `.env` file (see `.env.sample`):

   ```pwsh
   azd env get-values > .env
   ```

## Run the interactive voice client

```pwsh
.venv\Scripts\Activate.ps1
python -m src.voice_live_agents_quickstart
```

Speak to the agent; press `Ctrl+C` to exit. Each session writes to `logs/`:

- `<timestamp>_voicelive.log` — technical log
- `<timestamp>_conversation.log` — user/agent transcripts
- `<timestamp>_latency.csv` + `<timestamp>_latency_summary.json` — latency metrics

## Latency metrics

Captured per session:

| Metric | Definition |
| --- | --- |
| `session_ready_ms` | `connect()` start → `SESSION_UPDATED` |
| `greeting_ttfb_ms` | `SESSION_UPDATED` → first greeting `RESPONSE_AUDIO_DELTA` |
| `turn_ttfb_ms` | `INPUT_AUDIO_BUFFER_SPEECH_STOPPED` → first `RESPONSE_AUDIO_DELTA` |
| `turn_total_ms` | `INPUT_AUDIO_BUFFER_SPEECH_STOPPED` → `RESPONSE_DONE` |

The summary JSON includes count / min / avg / p50 / p95 / max per metric.

## End-to-end test

Replaces the microphone with a WAV fixture (`tests/e2e/fixtures/hello.wav`, generated at first run if absent), so the test runs without audio hardware.

```pwsh
$env:RUN_E2E="1"
pytest -m e2e -v
```

Asserts:

- A user transcript was received
- At least one `RESPONSE_AUDIO_DELTA` was emitted by the agent
- A `RESPONSE_DONE` was observed
- A positive TTFB was recorded

To use a real recording, drop a 24 kHz / 16-bit / mono WAV at `tests/e2e/fixtures/hello.wav`.

## Project layout

```
azure.yaml
infra/
  main.bicep
  voicelive.bicep
  foundry-roles.bicep
  main.parameters.json
scripts/
  postprovision.ps1
  postprovision.sh
src/
  audio_processor.py
  create_agent_with_voicelive.py
  metrics.py
  voice_assistant.py
  voice_live_agents_quickstart.py
tests/
  e2e/
    fake_audio_processor.py
    test_voice_agent_e2e.py
```

## Tear down

```pwsh
azd down
```

Removes only the Voice Live resource and role assignments. The existing Foundry project is untouched. The agent itself remains in the Foundry project — delete it manually from the portal if needed.
