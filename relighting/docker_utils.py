from __future__ import annotations

import json
import time
from typing import Optional

from .client import check_channel
from .connection import RelightingSetupSettings

try:
    from ..studio_voice.docker_utils import (
        CommandResult,
        ProgressCallback,
        _effective_key,
        _emit,
        _format_elapsed,
        _run,
        docker_gpu_check,
        docker_info,
        image_exists,
        ngc_login,
        pull_image as _pull_image,
    )
except ImportError:  # pragma: no cover - direct imports outside package mode.
    from studio_voice.docker_utils import (
        CommandResult,
        ProgressCallback,
        _effective_key,
        _emit,
        _format_elapsed,
        _run,
        docker_gpu_check,
        docker_info,
        image_exists,
        ngc_login,
        pull_image as _pull_image,
    )


DEFAULT_IMAGE = "nvcr.io/nim/nvidia/relighting:1.1.0"
DEFAULT_CONTAINER_NAME = "relighting-nim"
DEFAULT_TARGET = "127.0.0.1:8101"
DEFAULT_GRPC_HOST_PORT = 8101
DEFAULT_HTTP_HOST_PORT = 18100
DEFAULT_METRICS_HOST_PORT = 19002
DEFAULT_WAIT_TIMEOUT_S = 1200.0
DEFAULT_NGC_USERNAME = "$oauthtoken"


def pull_image(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    username: str = DEFAULT_NGC_USERNAME,
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    result = _pull_image(
        api_key,
        image=image,
        username=username,
        progress=progress,
        image_label="Relighting",
        access_instructions=(
            "The image name matches NVIDIA's Relighting NIM deployment documentation. "
            "If pull access is denied, open "
            "https://docs.nvidia.com/nim/maxine/relighting/latest/getting-started.html "
            "while signed in, accept the Relighting NIM terms if prompted, then generate or reuse an "
            "NGC Personal API key with the NGC Catalog service enabled. Your NGC account must also "
            "have access to this downloadable NIM."
        ),
    )
    if result.ok:
        return CommandResult(True, f"Relighting image is ready: {image}")
    return result


def container_status(container_name: str = DEFAULT_CONTAINER_NAME) -> str:
    result = _run(["docker", "inspect", "-f", "{{.State.Status}}", container_name], timeout_s=30)
    if not result.ok:
        return "missing"
    return result.output.strip()


def container_port_map(container_name: str = DEFAULT_CONTAINER_NAME) -> dict[str, list[dict[str, str]]]:
    result = _run(["docker", "inspect", "-f", "{{json .NetworkSettings.Ports}}", container_name], timeout_s=30)
    if not result.ok:
        return {}
    try:
        parsed = json.loads(result.output)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def container_has_conflicting_or_wrong_ports(
    container_name: str,
    settings: RelightingSetupSettings,
) -> bool:
    ports = container_port_map(container_name)
    if not ports:
        return True
    expected = {
        "8000/tcp": str(settings.http_host_port),
        "8001/tcp": str(settings.grpc_host_port),
        "9002/tcp": str(settings.metrics_host_port),
    }
    blocked_comfy_ports = {"8000", "8001"}
    for container_port, expected_host in expected.items():
        bindings = ports.get(container_port)
        if not isinstance(bindings, list) or not bindings:
            return True
        host_ports = {str(binding.get("HostPort")) for binding in bindings if isinstance(binding, dict)}
        if expected_host not in host_ports:
            return True
        if container_port != "8001/tcp" and host_ports & blocked_comfy_ports:
            return True
    return False


def start_relighting_container(
    *,
    api_key: str,
    settings: RelightingSetupSettings,
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    key = _effective_key(api_key)
    _emit(progress, "Container phase: checking existing Relighting container.")
    status = container_status(settings.container_name)
    if status != "missing" and container_has_conflicting_or_wrong_ports(settings.container_name, settings):
        _emit(
            progress,
            "Container phase: existing Relighting container has old or conflicting port mappings. "
            "Recreating it with HTTP "
            f"{settings.http_host_port}:8000, gRPC {settings.grpc_host_port}:8001, "
            f"metrics {settings.metrics_host_port}:9002.",
        )
        removed = _run(["docker", "rm", "-f", settings.container_name], timeout_s=120)
        if not removed.ok:
            return removed
        status = "missing"

    if status == "running":
        _emit(progress, f"Container phase: {settings.container_name} is already running.")
        return CommandResult(True, f"{settings.container_name} is already running on gRPC port {settings.grpc_host_port}.")

    if status not in ("missing", ""):
        _emit(progress, f"Container phase: starting existing stopped container {settings.container_name}.")
        started = _run(["docker", "start", settings.container_name], timeout_s=120)
        if started.ok:
            return CommandResult(True, f"{settings.container_name} started on gRPC port {settings.grpc_host_port}.")
        return started

    if settings.force_pull or not image_exists(settings.image):
        _emit(progress, "Image phase: Relighting image is missing or force_pull is enabled.")
        pull = pull_image(key, image=settings.image, username=settings.ngc_username, progress=progress)
        if not pull.ok:
            return pull
    else:
        _emit(progress, f"Image phase: reusing existing Relighting image {settings.image}.")

    _emit(progress, "Container phase: creating Relighting container.")
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        settings.container_name,
        "--runtime=nvidia",
        "--gpus",
        "all",
        "--shm-size=8GB",
        "-e",
        f"NGC_API_KEY={key}",
        "-p",
        f"{settings.http_host_port}:8000",
        "-p",
        f"{settings.grpc_host_port}:8001",
        "-p",
        f"{settings.metrics_host_port}:9002",
    ]
    if settings.manifest_profile.strip():
        args.extend(["-e", f"NIM_MANIFEST_PROFILE={settings.manifest_profile.strip()}"])
    args.append(settings.image)

    result = _run(args, timeout_s=300)
    if result.ok:
        return CommandResult(
            True,
            f"{settings.container_name} is starting. gRPC is on host port {settings.grpc_host_port}; "
            f"NIM HTTP is on host port {settings.http_host_port}; metrics are on host port {settings.metrics_host_port}.",
        )
    return result


def setup_all_relighting(
    *,
    api_key: str,
    settings: RelightingSetupSettings,
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    steps: list[str] = []

    _emit(progress, "Step 1/5: Checking Docker Desktop.")
    info = docker_info()
    if not info.ok:
        return CommandResult(False, "Docker check failed:\n" + info.output)
    steps.append("Docker Desktop: " + info.output)

    _emit(progress, "Step 2/5: Checking GPU access from Docker.")
    gpu = docker_gpu_check(progress=progress)
    if not gpu.ok:
        return CommandResult(False, "Docker GPU check failed:\n" + gpu.output)
    gpu_summary = "GPU container check passed."
    for line in gpu.output.splitlines():
        if "GPU Device" in line or "Compute" in line:
            gpu_summary = line.strip()
            break
    steps.append(gpu_summary)

    _emit(progress, "Step 3/5: NGC login, image pull/reuse, and container start.")
    started = start_relighting_container(api_key=api_key, settings=settings, progress=progress)
    if not started.ok:
        return CommandResult(False, "Relighting container setup failed:\n" + started.output)
    steps.append(started.output)

    _emit(progress, "Step 4/5: Waiting for Relighting gRPC endpoint.")
    deadline = time.time() + float(settings.wait_timeout_s)
    wait_start = time.time()
    last_wait_log = 0.0
    last_error = ""
    while time.time() < deadline:
        error = check_channel(target=settings.target, timeout_s=5.0)
        if error is None:
            steps.append(f"Relighting gRPC is reachable at {settings.target}.")
            _emit(progress, "Step 5/5: Relighting is ready.")
            return CommandResult(True, "\n".join(steps))
        last_error = error
        now = time.time()
        if now - last_wait_log >= 30.0:
            remaining = max(0.0, deadline - now)
            _emit(
                progress,
                "Waiting for Relighting gRPC endpoint: "
                f"elapsed {_format_elapsed(now - wait_start)}, "
                f"remaining {_format_elapsed(remaining)}. "
                f"Last error: {_friendly_grpc_wait_error(last_error)}",
            )
            last_wait_log = now
        time.sleep(5.0)

    steps.append(f"Timed out waiting for Relighting gRPC at {settings.target}. Last error: {last_error}")
    return CommandResult(False, "\n".join(steps))


def _friendly_grpc_wait_error(error: str) -> str:
    if "FutureTimeoutError" in error:
        return "gRPC endpoint is still warming up."
    if "UNAVAILABLE" in error:
        return "gRPC endpoint is not accepting requests yet."
    return error
