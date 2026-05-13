from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioVoiceConnection:
    target: str = "127.0.0.1:8001"
    model_type: str = "48k-hq"
    streaming: bool = False
    ready: bool = False
    container_name: str = "studio-voice-nim"
    timeout_s: float = 120.0


@dataclass(frozen=True)
class StudioVoiceSetupSettings:
    image: str = "nvcr.io/nim/nvidia/studio-voice:latest"
    container_name: str = "studio-voice-nim"
    model_profile: str = ""
    file_size_limit: int = 36700160
    force_pull: bool = False
    target: str = "127.0.0.1:8001"
    model_type: str = "48k-hq"
    wait_timeout_s: float = 900.0
    ngc_username: str = "$oauthtoken"
