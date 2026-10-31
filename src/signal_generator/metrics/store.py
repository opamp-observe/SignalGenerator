# Copyright 2026 opamp.info
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

"""Immutable metric frame storage and independent thread-safe replay cursors."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from signal_generator.metrics.models import MetricFrame


class FrameExhaustedError(RuntimeError):
    """Indicate that an ``error`` EOF cursor was advanced past its final frame."""


@dataclass(frozen=True, slots=True)
class CursorSnapshot:
    """Read-only cursor diagnostics used by health and self-metrics."""

    next_index: int
    delivered: int
    exhausted: bool
    current_frame: int | str | None


class FrameStore:
    """Own a non-empty immutable sequence shared by any number of cursors."""

    def __init__(self, frames: tuple[MetricFrame, ...]) -> None:
        """Create a frame store after enforcing its non-empty invariant."""

        if not frames:
            raise ValueError("frame store requires at least one frame")
        self.frames = frames

    def cursor(self, eof_policy: str, name: str) -> FrameCursor:
        """Create a cursor whose position is independent from every other cursor."""

        return FrameCursor(self, eof_policy, name)


class FrameCursor:
    """Atomically allocate frames under the configured end-of-file policy."""

    def __init__(self, store: FrameStore, eof_policy: str, name: str) -> None:
        """Create a cursor at the first frame."""

        if eof_policy not in {"loop", "hold_last", "stop", "error"}:
            raise ValueError(f"unsupported EOF policy: {eof_policy}")
        self._store = store
        self._eof_policy = eof_policy
        self.name = name
        self._next_index = 0
        self._delivered = 0
        self._exhausted = False
        self._current_frame: int | str | None = None
        self._lock = threading.Lock()

    def next_frame(self) -> MetricFrame | None:
        """Return and advance one frame, or apply the configured EOF behavior."""

        with self._lock:
            frame = self._select_frame()
            if frame is not None:
                self._delivered += 1
                self._current_frame = frame.frame
            return frame

    def _select_frame(self) -> MetricFrame | None:
        """Select the next frame while the caller holds the cursor lock."""

        frames = self._store.frames
        if self._next_index < len(frames):
            frame = frames[self._next_index]
            self._next_index += 1
            return frame
        self._exhausted = True
        if self._eof_policy == "loop":
            self._next_index = 1
            self._exhausted = False
            return frames[0]
        if self._eof_policy == "hold_last":
            return frames[-1]
        if self._eof_policy == "stop":
            return None
        raise FrameExhaustedError(f"{self.name} cursor exhausted")

    def snapshot(self) -> CursorSnapshot:
        """Return cursor diagnostics without consuming or changing a frame."""

        with self._lock:
            return CursorSnapshot(
                self._next_index,
                self._delivered,
                self._exhausted,
                self._current_frame,
            )
