"""Fake AudioIO that streams a WAV file into the Voice Live connection.

Used by the E2E test to drive the assistant deterministically without a real
microphone or speakers.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from azure.ai.voicelive.aio import VoiceLiveConnection

logger = logging.getLogger(__name__)

# 24 kHz PCM16 mono, matching the Voice Live session config
SAMPLE_RATE = 24000
CHUNK_MS = 50
CHUNK_BYTES = int(SAMPLE_RATE * (CHUNK_MS / 1000.0)) * 2  # 2400 bytes


class FakeAudioProcessor:
    """AudioIO impl that pumps a WAV file into the input audio buffer."""

    def __init__(
        self,
        connection: "VoiceLiveConnection",
        wav_path: Path,
        trailing_silence_ms: int = 1500,
    ) -> None:
        self.connection = connection
        self.wav_path = wav_path
        self.trailing_silence_ms = trailing_silence_ms
        self.received_audio = bytearray()
        self._capture_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _read_pcm16_24k_mono(self) -> bytes:
        with wave.open(str(self.wav_path), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != SAMPLE_RATE:
                raise ValueError(
                    f"WAV fixture must be PCM16 mono {SAMPLE_RATE} Hz; got "
                    f"channels={w.getnchannels()} sampwidth={w.getsampwidth()} rate={w.getframerate()}"
                )
            return w.readframes(w.getnframes())

    async def _stream(self) -> None:
        try:
            audio_bytes = self._read_pcm16_24k_mono()
            silence = b"\x00" * (int(SAMPLE_RATE * (self.trailing_silence_ms / 1000.0)) * 2)
            payload = audio_bytes + silence
            for i in range(0, len(payload), CHUNK_BYTES):
                chunk = payload[i:i + CHUNK_BYTES]
                if not chunk:
                    break
                b64 = base64.b64encode(chunk).decode("utf-8")
                await self.connection.input_audio_buffer.append(audio=b64)
                # Real-time pacing: 50 ms per chunk
                await asyncio.sleep(CHUNK_MS / 1000.0)
            logger.info("FakeAudioProcessor finished streaming WAV (%d bytes)", len(payload))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("FakeAudioProcessor stream failed")
            raise

    def start_capture(self) -> None:
        if self._capture_task is not None:
            return
        self._loop = asyncio.get_event_loop()
        self._capture_task = self._loop.create_task(self._stream())

    def start_playback(self) -> None:
        # No-op: tests don't play audio.
        return

    def queue_audio(self, audio_data: Optional[bytes]) -> None:
        if audio_data:
            # Voice Live delivers audio deltas as base64-encoded strings.
            try:
                self.received_audio.extend(base64.b64decode(audio_data))
            except Exception:
                # If already bytes, append directly
                if isinstance(audio_data, (bytes, bytearray)):
                    self.received_audio.extend(audio_data)

    def skip_pending_audio(self) -> None:
        return

    def shutdown(self) -> None:
        if self._capture_task and not self._capture_task.done():
            self._capture_task.cancel()
