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

The existing Foundry (AI Services) account is **reused** for both the agent and the Voice Live endpoint — no new Foundry/Voice Live resource is created.

`azd up` only:

- Assigns the current user **Azure AI User** and **Cognitive Services User** on the existing Foundry account
- Runs the post-provision hook to install Python dependencies and create the agent (`src/create_agent_with_voicelive.py`)

`VOICELIVE_ENDPOINT` is set to the existing Foundry account's endpoint, per the [Voice Live quickstart](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-quickstart?tabs=foundry-new%2Cwindows%2Ckeyless&pivots=programming-language-python).

## Setup

1. Create and activate a Python virtual environment, install dependencies:

   ```pwsh
   py -3 -m venv .venv
   .venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Sign in:

   ```pwsh
   az login
   azd auth login
   ```

3. Create the azd environment:

   ```pwsh
   azd env new voice-agent-demo
   ```

4. Set all required azd env vars using the helper script (interactive — pre-fills with any existing values):

   ```pwsh
   ./scripts/set-azd-env.ps1
   ```

   Or non-interactively:

   ```pwsh
   ./scripts/set-azd-env.ps1 `
       -FoundryProjectEndpoint "https://<resource>.services.ai.azure.com/api/projects/<project>" `
       -FoundryResourceGroup   "<rg-of-foundry-resource>" `
       -FoundryResourceName    "<foundry-resource-name>" `
       -FoundryProjectName     "<project>" `
       -ModelDeploymentName    "gpt-4.1-mini" `
       -AgentName              "MyVoiceAgent" `
       -AzureLocation          "eastus2"
   ```

5. Provision and create the agent:

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

Removes only the role assignments created by `azd up`. The existing Foundry account and project are untouched. The agent itself remains in the Foundry project — delete it manually from the portal if needed.
