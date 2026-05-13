from __future__ import annotations

import logging

try:
    from comfy_api.latest import ComfyExtension, io
except ImportError:  # pragma: no cover - direct unit-style imports outside ComfyUI.
    ComfyExtension = object
    io = None

try:
    from .studio_voice.audio_utils import comfy_audio_to_numpy, expected_sample_rate, numpy_to_comfy_audio
    from .studio_voice.client import MODEL_TYPES, check_channel, enhance_audio
    from .studio_voice.connection import StudioVoiceConnection
    from .studio_voice.docker_utils import (
        DEFAULT_CONTAINER_NAME,
        DEFAULT_IMAGE,
        docker_gpu_check,
        docker_info,
        ngc_login,
        pull_image,
        setup_all_transactional,
        start_transactional_container,
    )
except ImportError:
    from studio_voice.audio_utils import comfy_audio_to_numpy, expected_sample_rate, numpy_to_comfy_audio
    from studio_voice.client import MODEL_TYPES, check_channel, enhance_audio
    from studio_voice.connection import StudioVoiceConnection
    from studio_voice.docker_utils import (
        DEFAULT_CONTAINER_NAME,
        DEFAULT_IMAGE,
        docker_gpu_check,
        docker_info,
        ngc_login,
        pull_image,
        setup_all_transactional,
        start_transactional_container,
    )


StudioVoiceConnectionIO = io.Custom("STUDIO_VOICE_CONNECTION")


class NvidiaStudioVoiceEnhance(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaStudioVoiceEnhance",
            display_name="NVIDIA Studio Voice Enhance",
            category="NVIDIA Maxine/Audio",
            description="Enhance recorded speech with a locally hosted NVIDIA Studio Voice NIM over gRPC.",
            search_aliases=["studio voice", "nvidia maxine", "enhance speech", "adobe podcast"],
            inputs=[
                io.Audio.Input("audio"),
                io.String.Input("target", default="127.0.0.1:8001", advanced=True),
                io.Combo.Input("model_type", options=list(MODEL_TYPES), default="48k-hq", advanced=True),
                io.Boolean.Input("streaming", default=False, advanced=True),
                io.Float.Input("timeout_s", default=120.0, min=1.0, max=3600.0, step=1.0, advanced=True),
                StudioVoiceConnectionIO.Input("studio_voice_connection", optional=True),
            ],
            outputs=[
                io.Audio.Output("enhanced_audio"),
            ],
        )

    @classmethod
    def execute(
        cls,
        audio,
        target,
        model_type,
        streaming,
        timeout_s,
        studio_voice_connection=None,
    ) -> io.NodeOutput:
        if studio_voice_connection is not None:
            target = studio_voice_connection.target
            model_type = studio_voice_connection.model_type
            streaming = studio_voice_connection.streaming
            if not getattr(studio_voice_connection, "ready", False):
                live_error = check_channel(target=target, timeout_s=5.0)
                if live_error is not None:
                    raise RuntimeError(
                        "Studio Voice is not ready at "
                        f"{target}. Run NVIDIA Studio Voice Docker Setup with action "
                        "setup_all_transactional and a valid NGC API key, then check the Setup node's "
                        f"status output. Docker/NIM details: {live_error}"
                    )

        audio_np, sample_rate = comfy_audio_to_numpy(audio)
        required_rate = expected_sample_rate(model_type)
        if sample_rate != required_rate:
            raise ValueError(
                f"Studio Voice model_type {model_type} requires {required_rate} Hz input, "
                f"but received {sample_rate} Hz. Resample before this node."
            )

        result_np, result_rate, _elapsed = enhance_audio(
            audio_np=audio_np,
            sample_rate=sample_rate,
            target=target,
            model_type=model_type,
            streaming=bool(streaming),
            timeout_s=float(timeout_s),
        )
        return io.NodeOutput(numpy_to_comfy_audio(result_np, result_rate))


class NvidiaStudioVoiceDockerSetup(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaStudioVoiceDockerSetup",
            display_name="NVIDIA Studio Voice Docker Setup",
            category="NVIDIA Maxine/Setup",
            description=(
                "User-friendly Windows Docker setup for local Studio Voice NIM. "
                "The NGC key is used in memory, but saved ComfyUI workflows may retain node input values."
            ),
            search_aliases=["studio voice setup", "nvidia nim setup", "ngc login", "docker setup"],
            inputs=[
                io.Combo.Input(
                    "action",
                    options=[
                        "setup_all_transactional",
                        "check_docker",
                        "check_gpu",
                        "ngc_login",
                        "pull_studio_voice",
                        "start_studio_voice_transactional",
                    ],
                    default="setup_all_transactional",
                ),
                io.String.Input(
                    "ngc_api_key",
                    default="",
                    multiline=False,
                    tooltip=(
                        "Paste the NGC API key here, or leave empty to use NGC_API_KEY from the "
                        "environment that launched ComfyUI."
                    ),
                ),
                io.String.Input("image", default=DEFAULT_IMAGE, advanced=True),
                io.String.Input("container_name", default=DEFAULT_CONTAINER_NAME, advanced=True),
                io.String.Input(
                    "model_profile",
                    default="",
                    advanced=True,
                    tooltip="Optional NIM_MODEL_PROFILE override. Leave empty to let NIM choose.",
                ),
                io.Int.Input(
                    "file_size_limit",
                    default=36700160,
                    min=1048576,
                    max=2147483647,
                    step=1048576,
                    advanced=True,
                ),
                io.Boolean.Input(
                    "force_pull",
                    default=False,
                    advanced=True,
                    tooltip="When false, existing images/containers are reused. Enable only to refresh the NIM image.",
                ),
                io.String.Input("target", default="127.0.0.1:8001", advanced=True),
                io.Combo.Input("model_type", options=list(MODEL_TYPES), default="48k-hq", advanced=True),
                io.Float.Input("wait_timeout_s", default=900.0, min=30.0, max=7200.0, step=30.0, advanced=True),
                io.String.Input(
                    "ngc_username",
                    default="$oauthtoken",
                    advanced=True,
                    tooltip="NVIDIA deploy docs use the literal username $oauthtoken for API-key Docker login.",
                ),
            ],
            outputs=[
                StudioVoiceConnectionIO.Output("studio_voice_connection"),
                io.String.Output("status"),
            ],
            not_idempotent=True,
        )

    @classmethod
    def execute(
        cls,
        action,
        ngc_api_key,
        image,
        container_name,
        model_profile,
        file_size_limit,
        force_pull,
        target,
        model_type,
        wait_timeout_s,
        ngc_username,
    ) -> io.NodeOutput:
        if model_type not in MODEL_TYPES:
            model_type = "48k-hq"
        try:
            file_size_limit = int(file_size_limit)
        except (TypeError, ValueError):
            file_size_limit = 36700160
        if file_size_limit < 1048576 or file_size_limit > 2147483647:
            file_size_limit = 36700160
        try:
            wait_timeout_s = float(wait_timeout_s)
        except (TypeError, ValueError):
            wait_timeout_s = 900.0
        if wait_timeout_s != wait_timeout_s or wait_timeout_s < 30.0 or wait_timeout_s > 7200.0:
            wait_timeout_s = 900.0
        if not isinstance(ngc_username, str) or not ngc_username.strip() or ngc_username.strip().isdigit():
            ngc_username = "$oauthtoken"

        if action == "check_docker":
            logging.info("[NVIDIA Studio Voice Setup] Checking Docker Desktop.")
            result = docker_info()
        elif action == "check_gpu":
            result = docker_gpu_check(progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg))
        elif action == "ngc_login":
            logging.info("[NVIDIA Studio Voice Setup] Logging into NGC.")
            result = ngc_login(ngc_api_key, username=ngc_username)
        elif action == "pull_studio_voice":
            logging.info("[NVIDIA Studio Voice Setup] Pulling Studio Voice image: %s", image)
            result = pull_image(
                ngc_api_key,
                image=image,
                username=ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg),
            )
        elif action == "start_studio_voice_transactional":
            logging.info("[NVIDIA Studio Voice Setup] Starting Studio Voice transactional container.")
            result = start_transactional_container(
                api_key=ngc_api_key,
                image=image,
                container_name=container_name,
                model_profile=model_profile,
                file_size_limit=file_size_limit,
                force_pull=bool(force_pull),
                username=ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg),
            )
        elif action == "setup_all_transactional":
            logging.info("[NVIDIA Studio Voice Setup] Starting full transactional setup.")
            result = setup_all_transactional(
                api_key=ngc_api_key,
                image=image,
                container_name=container_name,
                model_profile=model_profile,
                file_size_limit=file_size_limit,
                target=target,
                wait_timeout_s=wait_timeout_s,
                force_pull=bool(force_pull),
                username=ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg),
            )
        else:
            raise ValueError(f"Unknown setup action: {action}")

        ready = False
        health_line = ""
        if result.ok:
            health_error = check_channel(target=target, timeout_s=5.0)
            ready = health_error is None
            if ready:
                health_line = f"\nHealth: Studio Voice gRPC is reachable at {target}."
            else:
                health_line = f"\nHealth: Studio Voice gRPC is not reachable yet at {target}. Details: {health_error}"
        connection = StudioVoiceConnection(
            target=target,
            model_type=model_type,
            streaming=False,
            ready=ready,
            container_name=container_name,
        )
        prefix = "OK" if result.ok else "ERROR"
        return io.NodeOutput(connection, f"{prefix}: {result.output}{health_line}")


class NvidiaMaxineExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            NvidiaStudioVoiceDockerSetup,
            NvidiaStudioVoiceEnhance,
        ]


async def comfy_entrypoint() -> NvidiaMaxineExtension:
    return NvidiaMaxineExtension()
