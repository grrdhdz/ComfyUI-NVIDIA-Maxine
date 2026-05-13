from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioVoiceConnection:
    target: str = "127.0.0.1:8001"
    model_type: str = "48k-hq"
    streaming: bool = False
    ready: bool = False
    container_name: str = "studio-voice-nim"

