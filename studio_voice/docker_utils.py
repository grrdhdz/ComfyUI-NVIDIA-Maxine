from __future__ import annotations

import os
import subprocess
import time
from typing import Callable
from dataclasses import dataclass
from typing import Optional

from .client import check_channel


DEFAULT_IMAGE = "nvcr.io/nim/nvidia/studio-voice:latest"
DEFAULT_CONTAINER_NAME = "studio-voice-nim"


@dataclass
class CommandResult:
    ok: bool
    output: str


ProgressCallback = Callable[[str], None]


def _emit(progress: Optional[ProgressCallback], message: str) -> None:
    if progress is not None:
        progress(message)


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
    last_emit = 0.0
    start = time.time()

    assert proc.stdout is not None
    while True:
        if time.time() - start > timeout_s:
            proc.kill()
            return CommandResult(False, f"Command timed out after {timeout_s:.0f}s: {' '.join(args)}")

        line = proc.stdout.readline()
        if line:
            cleaned = line.replace("\r", "\n").strip()
            if cleaned:
                output_lines.append(cleaned)
                now = time.time()
                # Docker can emit very chatty layer updates; throttle identical-style progress lines.
                if now - last_emit >= 1.0 or "Downloaded newer image" in cleaned or "Digest:" in cleaned:
                    _emit(progress, cleaned)
                    last_emit = now
            continue

        if proc.poll() is not None:
            break
        time.sleep(0.1)

    remaining = proc.stdout.read()
    if remaining:
        for part in remaining.replace("\r", "\n").splitlines():
            cleaned = part.strip()
            if cleaned:
                output_lines.append(cleaned)
                _emit(progress, cleaned)

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


def pull_image(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    username: str = "$oauthtoken",
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    _emit(progress, f"Logging into NGC as {username}.")
    login = ngc_login(api_key, username=username)
    if not login.ok:
        return CommandResult(False, "NGC Docker login failed:\n" + login.output)
    _emit(progress, f"Pulling Studio Voice image: {image}")
    pull = _run_streaming(["docker", "pull", image], timeout_s=3600, progress=progress)
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


def start_transactional_container(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    model_profile: str = "",
    file_size_limit: int = 36700160,
    force_pull: bool = False,
    username: str = "$oauthtoken",
    progress: Optional[ProgressCallback] = None,
) -> CommandResult:
    key = _effective_key(api_key)
    status = container_status(container_name)
    if status == "running":
        return CommandResult(True, f"{container_name} is already running on gRPC port 8001.")
    if status not in ("missing", ""):
        started = _run(["docker", "start", container_name], timeout_s=120)
        if started.ok:
            return CommandResult(True, f"{container_name} started on gRPC port 8001.")
        return started

    if force_pull or not image_exists(image):
        pull = pull_image(key, image=image, username=username, progress=progress)
        if not pull.ok:
            return pull

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
        "8000:8000",
        "-p",
        "8001:8001",
    ]
    if model_profile.strip():
        args.extend(["-e", f"NIM_MODEL_PROFILE={model_profile.strip()}"])
    args.append(image)

    result = _run(args, timeout_s=300)
    if result.ok:
        return CommandResult(True, f"{container_name} is starting. Wait for NIM logs, then use Health Check.")
    return result


def setup_all_transactional(
    api_key: str,
    image: str = DEFAULT_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    model_profile: str = "",
    file_size_limit: int = 36700160,
    target: str = "127.0.0.1:8001",
    wait_timeout_s: float = 900.0,
    force_pull: bool = False,
    username: str = "$oauthtoken",
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

    _emit(progress, "Step 3/5: Logging into NGC and preparing Studio Voice image/container.")
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
    while time.time() < deadline:
        error = check_channel(target=target, timeout_s=5.0)
        if error is None:
            steps.append(f"Studio Voice gRPC is reachable at {target}.")
            _emit(progress, "Step 5/5: Studio Voice is ready.")
            return CommandResult(True, "\n".join(steps))
        last_error = error
        time.sleep(5.0)

    steps.append(f"Timed out waiting for Studio Voice gRPC at {target}. Last error: {last_error}")
    return CommandResult(False, "\n".join(steps))
