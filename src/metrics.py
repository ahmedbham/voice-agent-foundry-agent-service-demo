"""Latency metrics recorder for the Voice Live demo.

Captures per-turn timings and writes a CSV plus JSON summary. Hook points
(driven by the voice assistant):

- `session_start`     -> recorded on `connect()` start
- `session_ready`     -> on `SESSION_UPDATED`            (=> session_ready_ms)
- `greeting_first_audio` -> on first RESPONSE_AUDIO_DELTA after session_ready
                            (=> greeting_ttfb_ms)
- `speech_stopped`    -> on INPUT_AUDIO_BUFFER_SPEECH_STOPPED (per turn)
- `response_first_audio` -> on next RESPONSE_AUDIO_DELTA after speech_stopped
                            (=> turn_ttfb_ms)
- `response_done`     -> on RESPONSE_DONE                (=> turn_total_ms)
"""
from __future__ import annotations

import csv
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TurnRecord:
    turn_id: int
    speech_stopped_at: float
    first_audio_at: Optional[float] = None
    response_done_at: Optional[float] = None

    @property
    def turn_ttfb_ms(self) -> Optional[float]:
        if self.first_audio_at is None:
            return None
        return (self.first_audio_at - self.speech_stopped_at) * 1000.0

    @property
    def turn_total_ms(self) -> Optional[float]:
        if self.response_done_at is None:
            return None
        return (self.response_done_at - self.speech_stopped_at) * 1000.0


@dataclass
class LatencyRecorder:
    session_start_at: Optional[float] = None
    session_ready_at: Optional[float] = None
    greeting_first_audio_at: Optional[float] = None
    turns: list[TurnRecord] = field(default_factory=list)
    _current_turn: Optional[TurnRecord] = None

    def session_start(self) -> None:
        self.session_start_at = time.monotonic()

    def session_ready(self) -> None:
        self.session_ready_at = time.monotonic()

    def greeting_first_audio(self) -> None:
        if self.greeting_first_audio_at is None:
            self.greeting_first_audio_at = time.monotonic()

    def speech_stopped(self) -> None:
        turn_id = len(self.turns) + 1
        self._current_turn = TurnRecord(
            turn_id=turn_id, speech_stopped_at=time.monotonic()
        )
        self.turns.append(self._current_turn)

    def response_first_audio(self) -> None:
        if self._current_turn and self._current_turn.first_audio_at is None:
            self._current_turn.first_audio_at = time.monotonic()

    def response_done(self) -> None:
        if self._current_turn and self._current_turn.response_done_at is None:
            self._current_turn.response_done_at = time.monotonic()
            self._current_turn = None

    @property
    def session_ready_ms(self) -> Optional[float]:
        if self.session_start_at is None or self.session_ready_at is None:
            return None
        return (self.session_ready_at - self.session_start_at) * 1000.0

    @property
    def greeting_ttfb_ms(self) -> Optional[float]:
        if self.session_ready_at is None or self.greeting_first_audio_at is None:
            return None
        return (self.greeting_first_audio_at - self.session_ready_at) * 1000.0

    def summary(self) -> dict:
        ttfbs = [t.turn_ttfb_ms for t in self.turns if t.turn_ttfb_ms is not None]
        totals = [t.turn_total_ms for t in self.turns if t.turn_total_ms is not None]

        def stats(values: list[float]) -> dict:
            if not values:
                return {"count": 0}
            sorted_v = sorted(values)
            return {
                "count": len(values),
                "min": min(values),
                "avg": statistics.fmean(values),
                "p50": statistics.median(sorted_v),
                "p95": sorted_v[max(0, int(len(sorted_v) * 0.95) - 1)] if len(sorted_v) > 1 else sorted_v[0],
                "max": max(values),
            }

        return {
            "session_ready_ms": self.session_ready_ms,
            "greeting_ttfb_ms": self.greeting_ttfb_ms,
            "turn_ttfb_ms": stats(ttfbs),
            "turn_total_ms": stats(totals),
            "turns": len(self.turns),
        }

    def flush(self, csv_path: Path, json_path: Path) -> None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["turn_id", "turn_ttfb_ms", "turn_total_ms"])
            for t in self.turns:
                writer.writerow([t.turn_id, t.turn_ttfb_ms, t.turn_total_ms])
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(self.summary(), f, indent=2)
