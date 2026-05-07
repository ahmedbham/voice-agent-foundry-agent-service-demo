"""Interactive voice agent client (mic + speakers).

Usage:
    az login
    python -m src.voice_live_agents_quickstart
"""
from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

import asyncio
import pyaudio
from dotenv import load_dotenv
from azure.identity.aio import AzureCliCredential

from .metrics import LatencyRecorder
from .voice_assistant import BasicVoiceAssistant


_script_dir = Path(__file__).resolve().parent
_repo_root = _script_dir.parent
load_dotenv(_repo_root / ".env", override=True)

_logs_dir = _repo_root / "logs"
_logs_dir.mkdir(exist_ok=True)
_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_conversation_log = _logs_dir / f"{_timestamp}_conversation.log"

logging.basicConfig(
    filename=str(_logs_dir / f"{_timestamp}_voicelive.log"),
    filemode="w",
    format="%(asctime)s:%(name)s:%(levelname)s:%(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _check_audio_devices() -> None:
    p = pyaudio.PyAudio()
    try:
        def _has_channels(key):
            return any(
                (p.get_device_info_by_index(i).get(key, 0) or 0) > 0
                for i in range(p.get_device_count())
            )
        if not _has_channels("maxInputChannels"):
            sys.exit("No audio input devices found. Please check your microphone.")
        if not _has_channels("maxOutputChannels"):
            sys.exit("No audio output devices found. Please check your speakers.")
    finally:
        p.terminate()


def main() -> None:
    endpoint = os.environ.get("VOICELIVE_ENDPOINT", "")
    voice_name = os.environ.get("VOICE_NAME", "en-US-Ava:DragonHDLatestNeural")
    agent_name = os.environ.get("AGENT_NAME", "")
    agent_version = os.environ.get("AGENT_VERSION") or None
    project_name = os.environ.get("PROJECT_NAME", "")
    conversation_id = os.environ.get("CONVERSATION_ID") or None
    foundry_resource_override = os.environ.get("FOUNDRY_RESOURCE_OVERRIDE") or None
    agent_auth_id = os.environ.get("AGENT_AUTHENTICATION_IDENTITY_CLIENT_ID") or None
    api_version = os.environ.get("VOICELIVE_API_VERSION", "2026-01-01-preview")

    print("Environment variables:")
    print(f"  VOICELIVE_ENDPOINT: {endpoint}")
    print(f"  VOICE_NAME:         {voice_name}")
    print(f"  AGENT_NAME:         {agent_name}")
    print(f"  AGENT_VERSION:      {agent_version}")
    print(f"  PROJECT_NAME:       {project_name}")

    if not endpoint or not agent_name or not project_name:
        sys.exit("Set VOICELIVE_ENDPOINT, AGENT_NAME, and PROJECT_NAME in your .env file.")

    credential = AzureCliCredential()
    logger.info("Using Azure CLI credential")

    recorder = LatencyRecorder()
    assistant = BasicVoiceAssistant(
        endpoint=endpoint,
        credential=credential,
        voice=voice_name,
        agent_name=agent_name,
        project_name=project_name,
        agent_version=agent_version,
        conversation_id=conversation_id,
        foundry_resource_override=foundry_resource_override,
        agent_authentication_identity_client_id=agent_auth_id,
        api_version=api_version,
        latency_recorder=recorder,
        conversation_log_path=_conversation_log,
    )

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    try:
        asyncio.run(assistant.start())
    except KeyboardInterrupt:
        print("\n\U0001F44B Voice assistant shut down. Goodbye!")
    except Exception as e:
        print("Fatal Error:", e)
    finally:
        csv_path = _logs_dir / f"{_timestamp}_latency.csv"
        json_path = _logs_dir / f"{_timestamp}_latency_summary.json"
        try:
            recorder.flush(csv_path, json_path)
            print(f"Latency metrics written: {csv_path}")
        except Exception:
            logger.exception("Failed to write latency metrics")


if __name__ == "__main__":
    try:
        _check_audio_devices()
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"Audio system check failed: {e}")
    print("\U0001F399 Foundry Voice Agent with Azure VoiceLive SDK (Agent Mode)")
    print("=" * 65)
    main()
