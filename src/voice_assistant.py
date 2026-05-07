"""BasicVoiceAssistant: refactored from the Foundry Voice Live quickstart.

Differences vs. the quickstart:

- `AudioIO` is injected via `audio_io_factory` so tests can substitute a fake
  microphone/speaker.
- `LatencyRecorder` is injected to capture per-turn timings.
- A `done_event` exposes session completion to callers (e.g., E2E test).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING, Union

from azure.core.credentials import AzureKeyCredential
from azure.core.credentials_async import AsyncTokenCredential

from azure.ai.voicelive.aio import connect, AgentSessionConfig
from azure.ai.voicelive.models import (
    InputAudioFormat,
    InputTextContentPart,
    InterimResponseTrigger,
    LlmInterimResponseConfig,
    MessageItem,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerEventType,
)

from .audio_processor import AudioIO, AudioProcessor
from .metrics import LatencyRecorder

if TYPE_CHECKING:
    from azure.ai.voicelive.aio import VoiceLiveConnection

logger = logging.getLogger(__name__)

AudioIOFactory = Callable[["VoiceLiveConnection"], AudioIO]


class BasicVoiceAssistant:
    """Voice assistant that connects to Foundry Agent via Voice Live."""

    def __init__(
        self,
        endpoint: str,
        credential: Union[AzureKeyCredential, AsyncTokenCredential],
        voice: str,
        agent_name: str,
        project_name: str,
        agent_version: Optional[str] = None,
        conversation_id: Optional[str] = None,
        foundry_resource_override: Optional[str] = None,
        agent_authentication_identity_client_id: Optional[str] = None,
        api_version: str = "2026-01-01-preview",
        audio_io_factory: AudioIOFactory = AudioProcessor,
        latency_recorder: Optional[LatencyRecorder] = None,
        conversation_log_path: Optional[Path] = None,
        on_event: Optional[Callable[[Any], Awaitable[None]]] = None,
    ):
        self.endpoint = endpoint
        self.credential = credential
        self.voice = voice
        self.api_version = api_version
        self.agent_config: AgentSessionConfig = {
            "agent_name": agent_name,
            "agent_version": agent_version or None,
            "project_name": project_name,
            "conversation_id": conversation_id or None,
            "foundry_resource_override": foundry_resource_override or None,
            "authentication_identity_client_id": (
                agent_authentication_identity_client_id
                if agent_authentication_identity_client_id and foundry_resource_override
                else None
            ),
        }

        self.audio_io_factory = audio_io_factory
        self.latency_recorder = latency_recorder or LatencyRecorder()
        self.conversation_log_path = conversation_log_path
        self.on_event = on_event

        self.connection: Optional["VoiceLiveConnection"] = None
        self.audio_processor: Optional[AudioIO] = None
        self.session_ready = False
        self.greeting_sent = False
        self._active_response = False
        self._response_api_done = False
        self._awaiting_turn_first_audio = False
        self._awaiting_greeting_first_audio = False
        self.done_event: asyncio.Event = asyncio.Event()

    async def _write_conversation_log(self, message: str) -> None:
        if not self.conversation_log_path:
            return
        path = self.conversation_log_path
        await asyncio.to_thread(
            lambda: open(path, "a", encoding="utf-8").write(message + "\n")
        )

    async def start(self) -> None:
        self.latency_recorder.session_start()
        try:
            logger.info(
                "Connecting to VoiceLive API with agent %s for project %s",
                self.agent_config.get("agent_name"),
                self.agent_config.get("project_name"),
            )
            async with connect(
                endpoint=self.endpoint,
                credential=self.credential,
                api_version=self.api_version,
                agent_config=self.agent_config,
            ) as connection:
                self.connection = connection
                self.audio_processor = self.audio_io_factory(connection)

                await self._setup_session()
                self.audio_processor.start_playback()

                logger.info("Voice assistant ready! Start speaking...")
                print("\n" + "=" * 65)
                print("\U0001F3A4 VOICE ASSISTANT READY")
                print("Start speaking to begin conversation")
                print("Press Ctrl+C to exit")
                print("=" * 65 + "\n")

                await self._process_events()
        finally:
            if self.audio_processor:
                self.audio_processor.shutdown()
            self.done_event.set()

    async def _setup_session(self) -> None:
        logger.info("Setting up voice conversation session...")
        interim_response_config = LlmInterimResponseConfig(
            triggers=[InterimResponseTrigger.TOOL, InterimResponseTrigger.LATENCY],
            latency_threshold_ms=100,
            instructions=(
                "Create friendly interim responses indicating wait time due to "
                "ongoing processing, if any. Do not include in all responses! "
                "Do not say you don't have real-time access to information when calling tools!"
            ),
        )
        session_config = RequestSession(
            modalities=[Modality.TEXT, Modality.AUDIO],
            input_audio_format=InputAudioFormat.PCM16,
            output_audio_format=OutputAudioFormat.PCM16,
            interim_response=interim_response_config,
        )
        if self.connection is None:
            raise RuntimeError("Connection must be established before setting up session")
        await self.connection.session.update(session=session_config)
        logger.info("Session configuration sent")

    async def _process_events(self) -> None:
        if self.connection is None:
            raise RuntimeError("Connection must be established before processing events")
        try:
            async for event in self.connection:
                await self._handle_event(event)
        except Exception:
            logger.exception("Error processing events")
            raise

    async def _handle_event(self, event: Any) -> None:
        logger.debug("Received event: %s", event.type)
        ap = self.audio_processor
        conn = self.connection
        if ap is None or conn is None:
            raise RuntimeError("AudioProcessor and Connection must be initialized")

        if event.type == ServerEventType.SESSION_UPDATED:
            logger.info("Session ready: %s", event.session.id)
            self.latency_recorder.session_ready()
            s, a, v = event.session, event.session.agent, event.session.voice
            await self._write_conversation_log("\n".join([
                f"SessionID: {s.id}",
                f"Agent Name: {a.name}",
                f"Agent Description: {a.description}",
                f"Agent ID: {a.agent_id}",
                f"Voice Name: {v['name']}",
                f"Voice Type: {v['type']}",
                f"Voice Temperature: {v['temperature']}",
                "",
            ]))
            self.session_ready = True

            if not self.greeting_sent:
                self.greeting_sent = True
                self._awaiting_greeting_first_audio = True
                logger.info("Sending proactive greeting request")
                try:
                    await conn.conversation.item.create(
                        item=MessageItem(
                            role="system",
                            content=[
                                InputTextContentPart(
                                    text="Say something to welcome the user in English."
                                )
                            ],
                        )
                    )
                    await conn.response.create()
                except Exception:
                    logger.exception("Failed to send proactive greeting request")

            ap.start_capture()

        elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
            transcript = event.get("transcript", "") if hasattr(event, "get") else getattr(event, "transcript", "")
            print(f"\U0001F464 You said:\t{transcript}")
            await self._write_conversation_log(f"User Input:\t{transcript}")

        elif event.type == ServerEventType.RESPONSE_TEXT_DONE:
            text = event.get("text", "") if hasattr(event, "get") else getattr(event, "text", "")
            print(f"\U0001F916 Agent responded with text:\t{text}")
            await self._write_conversation_log(f"Agent Text Response:\t{text}")

        elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
            transcript = event.get("transcript", "") if hasattr(event, "get") else getattr(event, "transcript", "")
            print(f"\U0001F916 Agent responded with audio transcript:\t{transcript}")
            await self._write_conversation_log(f"Agent Audio Response:\t{transcript}")

        elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
            logger.info("User started speaking - stopping playback")
            print("\U0001F3A4 Listening...")
            ap.skip_pending_audio()
            if self._active_response and not self._response_api_done:
                try:
                    await conn.response.cancel()
                    logger.debug("Cancelled in-progress response due to barge-in")
                except Exception as e:
                    if "no active response" in str(e).lower():
                        logger.debug("Cancel ignored - response already completed")
                    else:
                        logger.warning("Cancel failed: %s", e)

        elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STOPPED:
            logger.info("User stopped speaking")
            print("\U0001F914 Processing...")
            self.latency_recorder.speech_stopped()
            self._awaiting_turn_first_audio = True

        elif event.type == ServerEventType.RESPONSE_CREATED:
            logger.info("Assistant response created")
            self._active_response = True
            self._response_api_done = False

        elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
            logger.debug("Received audio delta")
            if self._awaiting_turn_first_audio:
                self.latency_recorder.response_first_audio()
                self._awaiting_turn_first_audio = False
            elif self._awaiting_greeting_first_audio:
                self.latency_recorder.greeting_first_audio()
                self._awaiting_greeting_first_audio = False
            ap.queue_audio(event.delta)

        elif event.type == ServerEventType.RESPONSE_AUDIO_DONE:
            logger.info("Assistant finished speaking")
            print("\U0001F3A4 Ready for next input...")

        elif event.type == ServerEventType.RESPONSE_DONE:
            logger.info("Response complete")
            self.latency_recorder.response_done()
            self._active_response = False
            self._response_api_done = True

        elif event.type == ServerEventType.ERROR:
            msg = event.error.message
            if "Cancellation failed: no active response" in msg:
                logger.debug("Benign cancellation error: %s", msg)
            else:
                logger.error("VoiceLive error: %s", msg)
                print(f"Error: {msg}")

        elif event.type == ServerEventType.CONVERSATION_ITEM_CREATED:
            logger.debug("Conversation item created: %s", event.item.id)

        else:
            logger.debug("Unhandled event type: %s", event.type)

        if self.on_event is not None:
            try:
                await self.on_event(event)
            except Exception:
                logger.exception("on_event callback raised")
