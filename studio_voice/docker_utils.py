from __future__ import annotations

import os
import json
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable
from typing import Optional

from .client import check_channel


DEFAULT_IMAGE = "nvcr.io/nim/nvidia/studio-voice:latest"
DEFAULT_CONTAINER_NAME = "studio-voice-nim"
DEFAULT_TARGET = "127.0.0.1:8001"
DEFAULT_MODEL_TYPE = "48k-hq"
DEFAULT_FILE_SIZE_LIMIT = 36700160
DEFAULT_WAIT_TIMEOUT_S = 900.0
DEFAULT_NGC_USERNAME = "$oauthtoken"
DEFAULT_HTTP_HOST_PORT = 18000
PULL_HEARTBEAT_S = 30.0
PULL_SUMMARY_S = 5.0


@dataclass
class CommandResult:
    ok: bool
    output: str


ProgressCallback = Callable[[str], None]


def _emit(progress: Optional[ProgressCallback], message: str) -> None:
    if progress is not None:
        progress(message)


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _friendly_grpc_wait_error(error: str) -> str:
    if "FutureTimeoutError" in error:
        return "gRPC endpoint is still warming up."
    return error


def _format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(max(0.0, value))
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0


def _parse_size(value: str, unit: str) -> float:
    scale = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "TiB": 1024**4,
    }.get(unit, 1)
    return float(value) * scale


class DockerPullProgress:
    _layer_re = re.compile(r"^([a-f0-9]{8,64}):\s+(.+)$", re.IGNORECASE)
    _bytes_re = re.compile(
        r"([\d.]+)\s*([KMGT]?i?B|kB)?\s*/\s*([\d.]+)\s*([KMGT]?i?B|kB)?",
        re.IGNORECASE,
    )

    def __init__(self, progress: Optional[ProgressCallback]) -> None:
        self.progress = progress
        self.layers: dict[str, dict[str, object]] = {}
        self.start = time.time()
        self.last_summary = 0.0
        self.last_heartbeat = self.start
        self.last_signature = ""

    def consume_cli_line(self, line: str, force: bool = False) -> None:
        cleaned = " ".join(line.strip().split())
        if not cleaned:
            return
        matched = self._layer_re.match(cleaned)
        if matched:
            layer_id, status = matched.groups()
            self._update_layer(layer_id, status)
            if any(marker in status for marker in ("Download complete", "Pull complete")):
                self._emit_summary(force=True)
            else:
                self._emit_summary(force=force)
            return
        if cleaned.startswith("Digest:") or cleaned.startswith("Status:"):
            _emit(self.progress, cleaned)

    def consume_api_event(self, event: dict[str, object]) -> None:
        layer_id = str(event.get("id") or "").strip()
        status = str(event.get("status") or "").strip()
        detail = event.get("progressDetail")
        if layer_id and status:
            current = None
            total = None
            if isinstance(detail, dict):
                current_raw = detail.get("current")
                total_raw = detail.get("total")
                current = float(current_raw) if isinstance(current_raw, (int, float)) else None
                total = float(total_raw) if isinstance(total_raw, (int, float)) else None
            self._update_layer(layer_id, status, current=current, total=total)
            self._emit_summary(force=status in ("Download complete", "Pull complete"))
        elif status:
            _emit(self.progress, status)

    def heartbeat(self) -> None:
        now = time.time()
        if now - self.last_heartbeat < PULL_HEARTBEAT_S:
            return
        self.last_heartbeat = now
        total_layers = len(self.layers)
        pulled = self._count("Pull complete")
        downloaded = self._downloaded_layers()
        _emit(
            self.progress,
            "Pull still running: "
            f"elapsed {_format_elapsed(now - self.start)}, "
            f"{pulled}/{total_layers or '?'} layers pulled, "
            f"{downloaded}/{total_layers or '?'} downloaded.",
        )

    def final_summary(self) -> str:
        total_layers = len(self.layers)
        pulled = self._count("Pull complete")
        current, total = self._known_bytes()
        if total > 0:
            percent = min(100.0, (current / total) * 100.0)
            return (
                f"Pull progress finished: {percent:.1f}% known bytes, "
                f"{pulled}/{total_layers} layers pulled, "
                f"{_format_bytes(current)} / {_format_bytes(total)} known."
            )
        return f"Pull progress finished: {pulled}/{total_layers} layers pulled."

    def _update_layer(
        self,
        layer_id: str,
        status: str,
        current: Optional[float] = None,
        total: Optional[float] = None,
    ) -> None:
        layer = self.layers.setdefault(layer_id, {})
        layer["status"] = status
        if current is None or total is None:
            parsed = self._parse_progress_bytes(status)
            if parsed is not None:
                current, total = parsed
        if current is not None:
            layer["current"] = current
        if total is not None:
            layer["total"] = total
        if status in ("Download complete", "Pull complete"):
            known_total = layer.get("total")
            if isinstance(known_total, (int, float)):
                layer["current"] = float(known_total)

    def _parse_progress_bytes(self, text: str) -> Optional[tuple[float, float]]:
        matched = self._bytes_re.search(text)
        if not matched:
            return None
        current, current_unit, total, total_unit = matched.groups()
        unit = total_unit or current_unit or "B"
        return _parse_size(current, unit), _parse_size(total, unit)

    def _emit_summary(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self.last_summary < PULL_SUMMARY_S:
            return
        total_layers = len(self.layers)
        pulled = self._count("Pull complete")
        downloaded = self._downloaded_layers()
        current, total = self._known_bytes()
        if total > 0:
            percent = min(100.0, (current / total) * 100.0)
            signature = f"{percent:.1f}:{pulled}:{downloaded}:{total_layers}"
            message = (
                f"Pull progress: {percent:.1f}% known bytes | "
                f"{pulled}/{total_layers} layers pulled | "
                f"{downloaded}/{total_layers} downloaded | "
                f"{_format_bytes(current)} / {_format_bytes(total)} known."
            )
        else:
            signature = f"layers:{pulled}:{downloaded}:{total_layers}"
            message = (
                f"Pull progress: {pulled}/{total_layers or '?'} layers pulled | "
                f"{downloaded}/{total_layers or '?'} downloaded."
            )
        if force or signature != self.last_signature:
            _emit(self.progress, message)
            self.last_signature = signature
            self.last_summary = now
            self.last_heartbeat = now

    def _known_bytes(self) -> tuple[float, float]:
        current = 0.0
        total = 0.0
        for layer in self.layers.values():
            layer_total = layer.get("total")
            if not isinstance(layer_total, (int, float)) or layer_total <= 0:
                continue
            layer_current = layer.get("current")
            if not isinstance(layer_current, (int, float)):
                layer_current = 0.0
            total += float(layer_total)
            current += min(float(layer_current), float(layer_total))
        return current, total

    def _count(self, status: str) -> int:
        return sum(1 for layer in self.layers.values() if layer.get("status") == status)

    def _downloaded_layers(self) -> int:
        return sum(
            1
            for layer in self.layers.values()
            if layer.get("status") in ("Download complete", "Pull complete")
        )


def _run(
    args: list[str],
    input_text: Optional[str] = None,
    timeout_s: float = 600.0,
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    _emit(progress, "Running: " + " ".join(args))
    try:
        proc = subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(False, "Docker CLI was not found on PATH.")
    except subprocess.TimeoutExpired:
        return CommandResult(False, f"Command timed out after {timeout_s:.0f}s: {' '.join(args)}")

    combined = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    return CommandResult(proc.returncode == 0, combined)


def _run_streaming(
    args: list[str],
    input_text: Optional[str] = None,
    timeout_s: float = 3600.0,
    progress: Optional[ProgressCallback] = None,
    pull_progress: Optional[DockerPullProgress] = None,
) -> CommandResult:
    _emit(progress, "Running: " + " ".join(args))
    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        return CommandResult(False, "Docker CLI was not found on PATH.")

    if input_text is not None and proc.stdin is not None:
        proc.stdin.write(input_text)
        proc.stdin.close()

    output_lines: list[str] = []
    start = time.time()
    buffer = ""
    chunk_queue: queue.Queue[str | None] = queue.Queue()

    def read_stdout() -> None:
        assert proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.read(1)
                if not chunk:
                    break
                chunk_queue.put(chunk)
        finally:
            chunk_queue.put(None)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()

    while True:
        if time.time() - start > timeout_s:
            proc.kill()
            return CommandResult(False, f"Command timed out after {timeout_s:.0f}s: {' '.join(args)}")

        try:
            chunk = chunk_queue.get(timeout=0.2)
        except queue.Empty:
            if pull_progress is not None:
                pull_progress.heartbeat()
            if proc.poll() is not None:
                break
            continue

        if chunk is None:
            break

        if chunk:
            if chunk in ("\r", "\n"):
                cleaned = buffer.strip()
                buffer = ""
                if cleaned:
                    output_lines.append(cleaned)
                    if pull_progress is not None:
                        pull_progress.consume_cli_line(cleaned)
                    else:
                        _emit(progress, cleaned)
                continue
            buffer += chunk
            continue

    if buffer.strip():
        cleaned = buffer.strip()
        output_lines.append(cleaned)
        if pull_progress is not None:
            pull_progress.consume_cli_line(cleaned, force=True)
        else:
            _emit(progress, cleaned)

    if pull_progress is not None:
        _emit(progress, pull_progress.final_summary())

    proc.wait(timeout=5)
    combined = "\n".join(output_lines)
    return CommandResult(proc.returncode == 0, combined)


def _effective_key(api_key: str) -> str:
    key = (api_key or "").strip() or os.environ.get("NGC_API_KEY", "").strip()
    if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
        key = key[1:-1].strip()
    if not key:
        raise ValueError("Paste an NGC API key in the node, or set NGC_API_KEY before launching ComfyUI.")
    return key


def docker_info() -> CommandResult:
    return _run(["docker", "info", "--format", "{{.ServerVersion}} {{.OSType}} {{.OperatingSystem}}"], timeout_s=30)


def docker_gpu_check(progress: Optional[ProgressCallback] = None) -> CommandResult:
    _emit(progress, "Checking Docker GPU support with NVIDIA CUDA sample container.")
    return _run(
        [
            "docker",
            "run",
            "--rm",
            "--gpus=all",
            "nvcr.io/nvidia/k8s/cuda-sample:nbody",
            "nbody",
            "-gpu",
            "-benchmark",
        ],
        timeout_s=900,
        progress=progress,
    )


def ngc_login(api_key: str, username: str = "$oauthtoken") -> CommandResult:
    key = _effective_key(api_key)
    username = (username or "$oauthtoken").strip() or "$oauthtoken"
    result = _run(
        ["docker", "login", "nvcr.io", "--username", username, "--password-stdin"],
        input_text=key,
        timeout_s=120,
    )
    if result.ok:
        return CommandResult(True, "NGC Docker login succeeded.")
    return result


def _split_image(image: str) -> tuple[str, str]:
    if ":" not in image.rsplit("/", 1)[-1]:
        return image, "latest"
    repository, tag = image.rsplit(":", 1)
    return repository, tag


def _pull_image_engine_api(
    api_key: str,
    image: str,
    username: str,
    progress: Optional[ProgressCallback] = None,
) -> Optional[CommandResult]:
    try:
        import docker  # type: ignore[import-not-found]
    except Exception:
        return None

    repository, tag = _split_image(image)
    tracker = DockerPullProgress(progress)
    _emit(progress, "Using Docker Engine API pull stream for aggregate progress.")
    try:
        client = docker.APIClient()
        events = client.pull(
            repository,
            tag=tag,
            stream=True,
            decode=True,
            auth_config={"username": username, "password": api_key},
        )
        for event in events:
            if isinstance(event, dict):
                error = event.get("error")
                if error:
                    return CommandResult(False, str(error))
                tracker.consume_api_event(event)
                continue
            if isinstance(event, bytes):
                tracker.consume_cli_line(event.decode("utf-8", errors="replace"))
            else:
                tracker.consume_cli_line(str(event))
            tracker.heartbeat()
        _emit(progress, tracker.final_summary())
        return CommandResult(True, f"Studio Voice image is ready: {image}")
    except Exception as exc:
        _emit(
            progress,
            "Docker Engine API pull stream was unavailable; falling back to docker CLI. "
            f"Reason: {exc.__class__.__name__}: {exc}",
        )
        return None


def pull_image(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    username: str = DEFAULT_NGC_USERNAME,
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    _emit(progress, f"Logging into NGC as {username}.")
    login = ngc_login(api_key, username=username)
    if not login.ok:
        return CommandResult(False, "NGC Docker login failed:\n" + login.output)
    _emit(progress, f"Pulling Studio Voice image: {image}")
    key = _effective_key(api_key)
    pull = _pull_image_engine_api(key, image=image, username=username, progress=progress)
    if pull is None:
        tracker = DockerPullProgress(progress)
        pull = _run_streaming(
            ["docker", "pull", image],
            timeout_s=3600,
            progress=progress,
            pull_progress=tracker,
        )
    if pull.ok:
        return CommandResult(True, f"{login.output}\nStudio Voice image is ready: {image}")
    diagnostic = (
        f"{login.output}\n"
        f"Docker pull failed for {image}:\n{pull.output}\n\n"
        "The image name matches NVIDIA's Studio Voice NIM deployment documentation. "
        "If pull access is denied, open https://build.nvidia.com/nvidia/studiovoice/deploy "
        "while signed in, accept the Terms of Use for this NIM, then generate or reuse an "
        "NGC Personal API key with the NGC Catalog service enabled. Your NGC account must "
        "also have access to this downloadable NIM."
    )
    return CommandResult(False, diagnostic)


def image_exists(image: str = DEFAULT_IMAGE) -> bool:
    result = _run(["docker", "image", "inspect", image, "--format", "{{.Id}}"], timeout_s=30)
    return result.ok and bool(result.output.strip())


def container_status(container_name: str = DEFAULT_CONTAINER_NAME) -> str:
    result = _run(
        ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
        timeout_s=30,
    )
    if not result.ok:
        return "missing"
    return result.output.strip()


def container_has_legacy_comfy_port_mapping(container_name: str = DEFAULT_CONTAINER_NAME) -> bool:
    result = _run(
        ["docker", "inspect", "-f", "{{json .NetworkSettings.Ports}}", container_name],
        timeout_s=30,
    )
    if not result.ok:
        return False
    try:
        ports = json.loads(result.output)
    except json.JSONDecodeError:
        return False
    http_bindings = ports.get("8000/tcp") if isinstance(ports, dict) else None
    if not isinstance(http_bindings, list):
        return False
    return any(str(binding.get("HostPort")) == "8000" for binding in http_bindings if isinstance(binding, dict))


def start_transactional_container(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    model_profile: str = "",
    file_size_limit: int = DEFAULT_FILE_SIZE_LIMIT,
    force_pull: bool = False,
    username: str = DEFAULT_NGC_USERNAME,
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    key = _effective_key(api_key)
    _emit(progress, "Container phase: checking existing Studio Voice container.")
    status = container_status(container_name)
    if status != "missing" and container_has_legacy_comfy_port_mapping(container_name):
        _emit(
            progress,
            "Container phase: existing Studio Voice container uses host port 8000, "
            "which conflicts with Comfy Desktop. Recreating it with HTTP on host port "
            f"{DEFAULT_HTTP_HOST_PORT} and gRPC on host port 8001.",
        )
        removed = _run(["docker", "rm", "-f", container_name], timeout_s=120)
        if not removed.ok:
            return removed
        status = "missing"
    if status == "running":
        _emit(progress, f"Container phase: {container_name} is already running.")
        return CommandResult(True, f"{container_name} is already running on gRPC port 8001.")
    if status not in ("missing", ""):
        _emit(progress, f"Container phase: starting existing stopped container {container_name}.")
        started = _run(["docker", "start", container_name], timeout_s=120)
        if started.ok:
            return CommandResult(True, f"{container_name} started on gRPC port 8001.")
        return started

    if force_pull or not image_exists(image):
        _emit(progress, "Image phase: Studio Voice image is missing or force_pull is enabled.")
        pull = pull_image(key, image=image, username=username, progress=progress)
        if not pull.ok:
            return pull
    else:
        _emit(progress, f"Image phase: reusing existing Studio Voice image {image}.")

    _emit(progress, "Container phase: creating Studio Voice transactional container.")
    args = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--runtime=nvidia",
        "--gpus",
        "all",
        "--shm-size=8GB",
        "-e",
        f"NGC_API_KEY={key}",
        "-e",
        f"FILE_SIZE_LIMIT={int(file_size_limit)}",
        "-e",
        "STREAMING=false",
        "-p",
        f"{DEFAULT_HTTP_HOST_PORT}:8000",
        "-p",
        "8001:8001",
    ]
    if model_profile.strip():
        args.extend(["-e", f"NIM_MODEL_PROFILE={model_profile.strip()}"])
    args.append(image)

    result = _run(args, timeout_s=300)
    if result.ok:
        return CommandResult(
            True,
            f"{container_name} is starting. gRPC is on host port 8001; NIM HTTP is on host port {DEFAULT_HTTP_HOST_PORT}.",
        )
    return result


def setup_all_transactional(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    model_profile: str = "",
    file_size_limit: int = DEFAULT_FILE_SIZE_LIMIT,
    target: str = DEFAULT_TARGET,
    wait_timeout_s: float = DEFAULT_WAIT_TIMEOUT_S,
    force_pull: bool = False,
    username: str = DEFAULT_NGC_USERNAME,
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
    started = start_transactional_container(
        api_key=api_key,
        image=image,
        container_name=container_name,
        model_profile=model_profile,
        file_size_limit=file_size_limit,
        force_pull=force_pull,
        username=username,
        progress=progress,
    )
    if not started.ok:
        return CommandResult(False, "Studio Voice container setup failed:\n" + started.output)
    steps.append(started.output)

    _emit(progress, "Step 4/5: Waiting for Studio Voice gRPC endpoint.")
    deadline = time.time() + float(wait_timeout_s)
    last_error = ""
    wait_start = time.time()
    last_wait_log = 0.0
    while time.time() < deadline:
        error = check_channel(target=target, timeout_s=5.0)
        if error is None:
            steps.append(f"Studio Voice gRPC is reachable at {target}.")
            _emit(progress, "Step 5/5: Studio Voice is ready.")
            return CommandResult(True, "\n".join(steps))
        last_error = error
        now = time.time()
        if now - last_wait_log >= 30.0:
            remaining = max(0.0, deadline - now)
            _emit(
                progress,
                "Waiting for gRPC endpoint: "
                f"elapsed {_format_elapsed(now - wait_start)}, "
                f"remaining {_format_elapsed(remaining)}. "
                f"Status: {_friendly_grpc_wait_error(last_error)}",
            )
            last_wait_log = now
        time.sleep(5.0)

    steps.append(f"Timed out waiting for Studio Voice gRPC at {target}. Last error: {last_error}")
    return CommandResult(False, "\n".join(steps))
