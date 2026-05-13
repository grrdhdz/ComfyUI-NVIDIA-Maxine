from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelightingConnection:
    target: str = "127.0.0.1:8101"
    ready: bool = False
    container_name: str = "relighting-nim"
    timeout_s: float = 3600.0


@dataclass(frozen=True)
class RelightingSetupSettings:
    image: str = "nvcr.io/nim/nvidia/relighting:1.1.0"
    container_name: str = "relighting-nim"
    manifest_profile: str = ""
    force_pull: bool = False
    target: str = "127.0.0.1:8101"
    grpc_host_port: int = 8101
    http_host_port: int = 18100
    metrics_host_port: int = 19002
    wait_timeout_s: float = 1200.0
    ngc_username: str = "$oauthtoken"

