"""End-to-end test for the Voice Agent demo.

Requires:
- `azd up` already run (populates .env).
- `az login` complete (AzureCliCredential).
- RUN_E2E=1 env var to opt in.

Run:
    RUN_E2E=1 pytest -m e2e -v
"""
from __future__ import annotations

import asyncio
import os
import wave
from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv
from azure.ai.voicelive.models import ServerEventType
from azure.identity.aio import AzureCliCredential

from src.metrics import LatencyRecorder
from src.voice_assistant import BasicVoiceAssistant

from .fake_audio_processor import FakeAudioProcessor

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
WAV_PATH = FIXTURES_DIR / "hello.wav"


def _ensure_wav_fixture() -> None:
    """Generate a placeholder PCM16 24kHz mono WAV containing a tone if missing.

    A real recording of "hello" can be dropped into tests/e2e/fixtures/hello.wav
    to replace this placeholder.
    """
    if WAV_PATH.exists():
        return
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    import math
    sample_rate = 24000
    duration_s = 1.5
    freq = 220.0
    n_samples = int(sample_rate * duration_s)
    amplitude = 12000
    with wave.open(str(WAV_PATH), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for i in range(n_samples):
            sample = int(amplitude * math.sin(2 * math.pi * freq * (i / sample_rate)))
            w.writeframesraw(sample.to_bytes(2, byteorder="little", signed=True))


@pytest.mark.e2e
@pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="Set RUN_E2E=1 to run live E2E tests")
@pytest.mark.timeout(90)
async def test_voice_agent_end_to_end():
    load_dotenv(REPO_ROOT / ".env", override=True)
    _ensure_wav_fixture()

    endpoint = os.environ["VOICELIVE_ENDPOINT"]
    agent_name = os.environ["AGENT_NAME"]
    project_name = os.environ["PROJECT_NAME"]
    foundry_resource_override = os.environ.get("FOUNDRY_RESOURCE_OVERRIDE") or None
    api_version = os.environ.get("VOICELIVE_API_VERSION", "2026-01-01-preview")

    transcripts: list[str] = []
    audio_delta_count = 0
    response_done_seen = False
    fake_audio_holder: dict = {}

    async def on_event(event):
        nonlocal audio_delta_count, response_done_seen
        et = event.type
        if et == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            t = event.get("transcript", "") if hasattr(event, "get") else getattr(event, "transcript", "")
            if t:
                transcripts.append(t)
        elif et == ServerEventType.RESPONSE_AUDIO_DELTA:
            audio_delta_count += 1
        elif et == ServerEventType.RESPONSE_DONE:
            response_done_seen = True
            # We've completed at least one full turn after the greeting; stop the session.
            if len(transcripts) >= 1:
                # Closing the connection ends the async-for loop in BasicVoiceAssistant.
                conn = fake_audio_holder.get("assistant").connection
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass

    def factory(conn):
        fake = FakeAudioProcessor(conn, wav_path=WAV_PATH)
        fake_audio_holder["audio"] = fake
        return fake

    recorder = LatencyRecorder()
    credential = AzureCliCredential()
    assistant = BasicVoiceAssistant(
        endpoint=endpoint,
        credential=credential,
        voice=os.environ.get("VOICE_NAME", "en-US-Ava:DragonHDLatestNeural"),
        agent_name=agent_name,
        project_name=project_name,
        foundry_resource_override=foundry_resource_override,
        api_version=api_version,
        audio_io_factory=factory,
        latency_recorder=recorder,
        on_event=on_event,
    )
    fake_audio_holder["assistant"] = assistant

    try:
        await asyncio.wait_for(assistant.start(), timeout=80)
    except asyncio.TimeoutError:
        pytest.fail("E2E test timed out waiting for full turn")
    except Exception:
        # Closing the connection mid-stream may surface as an exception; ok if assertions pass.
        pass

    # Persist metrics
    logs_dir = REPO_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    recorder.flush(logs_dir / f"e2e_{ts}_latency.csv", logs_dir / f"e2e_{ts}_latency_summary.json")

    print("\nLatency summary:", recorder.summary())

    assert audio_delta_count > 0, "Expected at least one RESPONSE_AUDIO_DELTA event"
    assert response_done_seen, "Expected at least one RESPONSE_DONE event"
    # Greeting always fires; user transcription should fire once we stream audio.
    assert len(transcripts) >= 1, f"Expected user transcript; got: {transcripts}"
    # Latency assertions: TTFB should be > 0 for greeting OR for first turn
    assert (recorder.greeting_ttfb_ms or 0) > 0 or any(
        (t.turn_ttfb_ms or 0) > 0 for t in recorder.turns
    ), "Expected a positive TTFB measurement"
