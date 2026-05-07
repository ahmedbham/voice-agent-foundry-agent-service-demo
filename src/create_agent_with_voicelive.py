"""Create (or update) a Foundry agent with Voice Live configuration in metadata.

Run after `azd up` (or directly) to provision the agent referenced by the demo
client. The Voice Live session config is stored in the agent's metadata using
512-char chunks, as required by Foundry.
"""
from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition


def chunk_config(config_json: str, limit: int = 512) -> dict:
    """Split config into chunked metadata entries (512-char limit per entry)."""
    metadata = {"microsoft.voice-live.configuration": config_json[:limit]}
    remaining = config_json[limit:]
    chunk_num = 1
    while remaining:
        metadata[f"microsoft.voice-live.configuration.{chunk_num}"] = remaining[:limit]
        remaining = remaining[limit:]
        chunk_num += 1
    return metadata


def reassemble_config(metadata: dict) -> str:
    """Reassemble chunked Voice Live configuration."""
    config = metadata.get("microsoft.voice-live.configuration", "")
    chunk_num = 1
    while f"microsoft.voice-live.configuration.{chunk_num}" in metadata:
        config += metadata[f"microsoft.voice-live.configuration.{chunk_num}"]
        chunk_num += 1
    return config


def main() -> int:
    load_dotenv(override=True)

    project_endpoint = os.environ.get("PROJECT_ENDPOINT")
    agent_name = os.environ.get("AGENT_NAME")
    model_deployment_name = os.environ.get("MODEL_DEPLOYMENT_NAME")

    missing = [
        n for n, v in (
            ("PROJECT_ENDPOINT", project_endpoint),
            ("AGENT_NAME", agent_name),
            ("MODEL_DEPLOYMENT_NAME", model_deployment_name),
        ) if not v
    ]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )

    voice_live_config = {
        "session": {
            "voice": {
                "name": os.environ.get("VOICE_NAME", "en-US-Ava:DragonHDLatestNeural"),
                "type": "azure-standard",
                "temperature": 0.8,
            },
            "input_audio_transcription": {"model": "azure-speech"},
            "turn_detection": {
                "type": "azure_semantic_vad",
                "end_of_utterance_detection": {
                    "model": "semantic_detection_v1_multilingual"
                },
            },
            "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
            "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
        }
    }

    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model_deployment_name,
            instructions="You are a helpful assistant that answers general questions.",
        ),
        metadata=chunk_config(json.dumps(voice_live_config)),
    )
    print(f"Agent created: {agent.name} (version {agent.version})")

    retrieved_agent = project_client.agents.get(agent_name=agent_name)
    stored_metadata = (retrieved_agent.versions or {}).get("latest", {}).get("metadata", {})
    stored_config = reassemble_config(stored_metadata)
    if stored_config:
        print("\nVoice Live configuration:")
        print(json.dumps(json.loads(stored_config), indent=2))
    else:
        print("\nVoice Live configuration not found in agent metadata.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
