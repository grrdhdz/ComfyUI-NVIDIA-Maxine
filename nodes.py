from __future__ import annotations

import logging
from pathlib import Path

try:
    from comfy_api.latest import ComfyExtension, io
except ImportError:  # pragma: no cover - direct unit-style imports outside ComfyUI.
    ComfyExtension = object
    io = None

try:
    from .studio_voice.audio_utils import (
        comfy_audio_to_numpy,
        expected_sample_rate,
        numpy_to_comfy_audio,
        resample_comfy_audio,
    )
    from .studio_voice.client import check_channel, enhance_audio
    from .studio_voice.connection import StudioVoiceConnection, StudioVoiceSetupSettings
    from .studio_voice.docker_utils import (
        DEFAULT_CONTAINER_NAME,
        DEFAULT_FILE_SIZE_LIMIT,
        DEFAULT_IMAGE,
        DEFAULT_MODEL_TYPE,
        DEFAULT_NGC_USERNAME,
        DEFAULT_TARGET,
        DEFAULT_WAIT_TIMEOUT_S,
        docker_gpu_check,
        docker_info,
        ngc_login,
        pull_image,
        setup_all_transactional,
        start_transactional_container,
    )
except ImportError:
    from studio_voice.audio_utils import (
        comfy_audio_to_numpy,
        expected_sample_rate,
        numpy_to_comfy_audio,
        resample_comfy_audio,
    )
    from studio_voice.client import check_channel, enhance_audio
    from studio_voice.connection import StudioVoiceConnection, StudioVoiceSetupSettings
    from studio_voice.docker_utils import (
        DEFAULT_CONTAINER_NAME,
        DEFAULT_FILE_SIZE_LIMIT,
        DEFAULT_IMAGE,
        DEFAULT_MODEL_TYPE,
        DEFAULT_NGC_USERNAME,
        DEFAULT_TARGET,
        DEFAULT_WAIT_TIMEOUT_S,
        docker_gpu_check,
        docker_info,
        ngc_login,
        pull_image,
        setup_all_transactional,
        start_transactional_container,
    )

try:
    from .relighting.client import BACKGROUND_SOURCES, HDRI_PRESETS, check_channel as check_relighting_channel, relight_video
    from .relighting.connection import RelightingConnection, RelightingSetupSettings
    from .relighting.docker_utils import (
        DEFAULT_CONTAINER_NAME as DEFAULT_RELIGHTING_CONTAINER_NAME,
        DEFAULT_GRPC_HOST_PORT as DEFAULT_RELIGHTING_GRPC_HOST_PORT,
        DEFAULT_HTTP_HOST_PORT as DEFAULT_RELIGHTING_HTTP_HOST_PORT,
        DEFAULT_IMAGE as DEFAULT_RELIGHTING_IMAGE,
        DEFAULT_METRICS_HOST_PORT as DEFAULT_RELIGHTING_METRICS_HOST_PORT,
        DEFAULT_NGC_USERNAME as DEFAULT_RELIGHTING_NGC_USERNAME,
        DEFAULT_TARGET as DEFAULT_RELIGHTING_TARGET,
        DEFAULT_WAIT_TIMEOUT_S as DEFAULT_RELIGHTING_WAIT_TIMEOUT_S,
        docker_gpu_check as relighting_docker_gpu_check,
        docker_info as relighting_docker_info,
        ngc_login as relighting_ngc_login,
        pull_image as pull_relighting_image,
        setup_all_relighting,
        start_relighting_container,
    )
except ImportError:
    from relighting.client import BACKGROUND_SOURCES, HDRI_PRESETS, check_channel as check_relighting_channel, relight_video
    from relighting.connection import RelightingConnection, RelightingSetupSettings
    from relighting.docker_utils import (
        DEFAULT_CONTAINER_NAME as DEFAULT_RELIGHTING_CONTAINER_NAME,
        DEFAULT_GRPC_HOST_PORT as DEFAULT_RELIGHTING_GRPC_HOST_PORT,
        DEFAULT_HTTP_HOST_PORT as DEFAULT_RELIGHTING_HTTP_HOST_PORT,
        DEFAULT_IMAGE as DEFAULT_RELIGHTING_IMAGE,
        DEFAULT_METRICS_HOST_PORT as DEFAULT_RELIGHTING_METRICS_HOST_PORT,
        DEFAULT_NGC_USERNAME as DEFAULT_RELIGHTING_NGC_USERNAME,
        DEFAULT_TARGET as DEFAULT_RELIGHTING_TARGET,
        DEFAULT_WAIT_TIMEOUT_S as DEFAULT_RELIGHTING_WAIT_TIMEOUT_S,
        docker_gpu_check as relighting_docker_gpu_check,
        docker_info as relighting_docker_info,
        ngc_login as relighting_ngc_login,
        pull_image as pull_relighting_image,
        setup_all_relighting,
        start_relighting_container,
    )

try:
    import folder_paths
except ImportError:  # pragma: no cover - only outside ComfyUI.
    folder_paths = None


StudioVoiceConnectionIO = io.Custom("STUDIO_VOICE_CONNECTION")
StudioVoiceSetupSettingsIO = io.Custom("STUDIO_VOICE_SETUP_SETTINGS")
RelightingConnectionIO = io.Custom("RELIGHTING_CONNECTION")
RelightingSetupSettingsIO = io.Custom("RELIGHTING_SETUP_SETTINGS")


def _normalize_setup_settings(settings: StudioVoiceSetupSettings | None) -> StudioVoiceSetupSettings:
    if not isinstance(settings, StudioVoiceSetupSettings):
        settings = StudioVoiceSetupSettings()

    try:
        file_size_limit = int(settings.file_size_limit)
    except (TypeError, ValueError):
        file_size_limit = DEFAULT_FILE_SIZE_LIMIT
    if file_size_limit < 1048576 or file_size_limit > 2147483647:
        file_size_limit = DEFAULT_FILE_SIZE_LIMIT
    try:
        wait_timeout_s = float(settings.wait_timeout_s)
    except (TypeError, ValueError):
        wait_timeout_s = DEFAULT_WAIT_TIMEOUT_S
    if wait_timeout_s != wait_timeout_s or wait_timeout_s < 30.0 or wait_timeout_s > 7200.0:
        wait_timeout_s = DEFAULT_WAIT_TIMEOUT_S

    ngc_username = (settings.ngc_username or DEFAULT_NGC_USERNAME).strip() or DEFAULT_NGC_USERNAME
    if ngc_username.isdigit():
        ngc_username = DEFAULT_NGC_USERNAME

    return StudioVoiceSetupSettings(
        image=(settings.image or DEFAULT_IMAGE).strip() or DEFAULT_IMAGE,
        container_name=(settings.container_name or DEFAULT_CONTAINER_NAME).strip() or DEFAULT_CONTAINER_NAME,
        model_profile=(settings.model_profile or "").strip(),
        file_size_limit=file_size_limit,
        force_pull=bool(settings.force_pull),
        target=(settings.target or DEFAULT_TARGET).strip() or DEFAULT_TARGET,
        model_type=DEFAULT_MODEL_TYPE,
        wait_timeout_s=wait_timeout_s,
        ngc_username=ngc_username,
    )


def _settings_summary(settings: StudioVoiceSetupSettings, source: str) -> str:
    profile = settings.model_profile or "<auto>"
    return (
        f"Settings source: {source}\n"
        f"image={settings.image}\n"
        f"container_name={settings.container_name}\n"
        f"model_profile={profile}\n"
        f"file_size_limit={settings.file_size_limit}\n"
        f"force_pull={settings.force_pull}\n"
        f"target={settings.target}\n"
        f"model_type={settings.model_type}\n"
        f"wait_timeout_s={settings.wait_timeout_s:.0f}\n"
        f"ngc_username={settings.ngc_username}"
    )


def _normalize_relighting_settings(settings: RelightingSetupSettings | None) -> RelightingSetupSettings:
    if not isinstance(settings, RelightingSetupSettings):
        settings = RelightingSetupSettings()

    grpc_host_port = _safe_port(settings.grpc_host_port, DEFAULT_RELIGHTING_GRPC_HOST_PORT)
    http_host_port = _safe_port(settings.http_host_port, DEFAULT_RELIGHTING_HTTP_HOST_PORT)
    metrics_host_port = _safe_port(settings.metrics_host_port, DEFAULT_RELIGHTING_METRICS_HOST_PORT)
    try:
        wait_timeout_s = float(settings.wait_timeout_s)
    except (TypeError, ValueError):
        wait_timeout_s = DEFAULT_RELIGHTING_WAIT_TIMEOUT_S
    if wait_timeout_s != wait_timeout_s or wait_timeout_s < 30.0 or wait_timeout_s > 7200.0:
        wait_timeout_s = DEFAULT_RELIGHTING_WAIT_TIMEOUT_S

    ngc_username = (settings.ngc_username or DEFAULT_RELIGHTING_NGC_USERNAME).strip() or DEFAULT_RELIGHTING_NGC_USERNAME
    if ngc_username.isdigit():
        ngc_username = DEFAULT_RELIGHTING_NGC_USERNAME

    return RelightingSetupSettings(
        image=(settings.image or DEFAULT_RELIGHTING_IMAGE).strip() or DEFAULT_RELIGHTING_IMAGE,
        container_name=(settings.container_name or DEFAULT_RELIGHTING_CONTAINER_NAME).strip()
        or DEFAULT_RELIGHTING_CONTAINER_NAME,
        manifest_profile=(settings.manifest_profile or "").strip(),
        force_pull=bool(settings.force_pull),
        target=(settings.target or DEFAULT_RELIGHTING_TARGET).strip() or DEFAULT_RELIGHTING_TARGET,
        grpc_host_port=grpc_host_port,
        http_host_port=http_host_port,
        metrics_host_port=metrics_host_port,
        wait_timeout_s=wait_timeout_s,
        ngc_username=ngc_username,
    )


def _safe_port(value, default: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    if port < 1 or port > 65535:
        return default
    return port


def _relighting_settings_summary(settings: RelightingSetupSettings, source: str) -> str:
    profile = settings.manifest_profile or "<auto>"
    return (
        f"Settings source: {source}\n"
        f"image={settings.image}\n"
        f"container_name={settings.container_name}\n"
        f"manifest_profile={profile}\n"
        f"force_pull={settings.force_pull}\n"
        f"target={settings.target}\n"
        f"grpc_host_port={settings.grpc_host_port}\n"
        f"http_host_port={settings.http_host_port}\n"
        f"metrics_host_port={settings.metrics_host_port}\n"
        f"wait_timeout_s={settings.wait_timeout_s:.0f}\n"
        f"ngc_username={settings.ngc_username}"
    )


def _default_output_path(video_path: str) -> str:
    stem = Path(video_path).stem or "relighting"
    if folder_paths is not None:
        output_dir = Path(folder_paths.get_output_directory())
    else:
        output_dir = Path.cwd() / "output"
    return str(output_dir / f"{stem}_relighting.mp4")


class NvidiaStudioVoiceAdvancedSettings(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaStudioVoiceAdvancedSettings",
            display_name="NVIDIA Studio Voice Advanced Settings",
            category="NVIDIA Maxine/Setup",
            description="Optional technical overrides for the Studio Voice Docker Setup node.",
            search_aliases=["studio voice advanced", "nvidia nim settings", "docker settings"],
            inputs=[
                io.String.Input("image", default=DEFAULT_IMAGE),
                io.String.Input("container_name", default=DEFAULT_CONTAINER_NAME),
                io.String.Input(
                    "model_profile",
                    default="",
                    tooltip="Optional NIM_MODEL_PROFILE override. Leave empty to let NIM choose.",
                ),
                io.Int.Input(
                    "file_size_limit",
                    default=DEFAULT_FILE_SIZE_LIMIT,
                    min=1048576,
                    max=2147483647,
                    step=1048576,
                ),
                io.Boolean.Input(
                    "force_pull",
                    default=False,
                    tooltip="When false, existing images/containers are reused. Enable only to refresh the NIM image.",
                ),
                io.String.Input("target", default=DEFAULT_TARGET),
                io.Float.Input("wait_timeout_s", default=DEFAULT_WAIT_TIMEOUT_S, min=30.0, max=7200.0, step=30.0),
                io.String.Input(
                    "ngc_username",
                    default=DEFAULT_NGC_USERNAME,
                    tooltip="NVIDIA deploy docs use the literal username $oauthtoken for API-key Docker login.",
                ),
            ],
            outputs=[
                StudioVoiceSetupSettingsIO.Output("advanced_settings"),
            ],
        )

    @classmethod
    def execute(
        cls,
        image,
        container_name,
        model_profile,
        file_size_limit,
        force_pull,
        target,
        wait_timeout_s,
        ngc_username,
    ) -> io.NodeOutput:
        settings = _normalize_setup_settings(
            StudioVoiceSetupSettings(
                image=image,
                container_name=container_name,
                model_profile=model_profile,
                file_size_limit=file_size_limit,
                force_pull=force_pull,
                target=target,
                model_type=DEFAULT_MODEL_TYPE,
                wait_timeout_s=wait_timeout_s,
                ngc_username=ngc_username,
            )
        )
        return io.NodeOutput(settings)


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
                StudioVoiceConnectionIO.Input("studio_voice_connection", optional=True),
            ],
            outputs=[
                io.Audio.Output("enhanced_audio"),
            ],
            accept_all_inputs=True,
        )

    @classmethod
    def execute(
        cls,
        audio,
        studio_voice_connection=None,
        **kwargs,
    ) -> io.NodeOutput:
        target = kwargs.get("target", DEFAULT_TARGET)
        streaming = bool(kwargs.get("streaming", False))
        timeout_s = float(kwargs.get("timeout_s", 120.0))
        model_type = DEFAULT_MODEL_TYPE
        if studio_voice_connection is not None:
            target = studio_voice_connection.target
            streaming = studio_voice_connection.streaming
            timeout_s = getattr(studio_voice_connection, "timeout_s", timeout_s)
            if not getattr(studio_voice_connection, "ready", False):
                live_error = check_channel(target=target, timeout_s=5.0)
                if live_error is not None:
                    raise RuntimeError(
                        "Studio Voice is not ready at "
                        f"{target}. Run NVIDIA Studio Voice Docker Setup with action "
                        "setup_all_transactional and a valid NGC API key, then check the Setup node's "
                        f"status output. Docker/NIM details: {live_error}"
                    )

        required_rate = expected_sample_rate(model_type)
        prepared_audio, source_sample_rate, changed = resample_comfy_audio(audio, required_rate)
        if changed:
            logging.info(
                "[NVIDIA Studio Voice Enhance] Resampled audio automatically: %s Hz -> %s Hz for %s.",
                source_sample_rate,
                required_rate,
                model_type,
            )
        audio_np, sample_rate = comfy_audio_to_numpy(prepared_audio)

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
                StudioVoiceSetupSettingsIO.Input("advanced_settings", optional=True),
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
        advanced_settings=None,
    ) -> io.NodeOutput:
        settings_source = "Advanced Settings node" if advanced_settings is not None else "safe defaults"
        settings = _normalize_setup_settings(advanced_settings)

        if action == "check_docker":
            logging.info("[NVIDIA Studio Voice Setup] Checking Docker Desktop.")
            result = docker_info()
        elif action == "check_gpu":
            result = docker_gpu_check(progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg))
        elif action == "ngc_login":
            logging.info("[NVIDIA Studio Voice Setup] Logging into NGC.")
            result = ngc_login(ngc_api_key, username=settings.ngc_username)
        elif action == "pull_studio_voice":
            logging.info("[NVIDIA Studio Voice Setup] Pulling Studio Voice image: %s", settings.image)
            result = pull_image(
                ngc_api_key,
                image=settings.image,
                username=settings.ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg),
            )
        elif action == "start_studio_voice_transactional":
            logging.info("[NVIDIA Studio Voice Setup] Starting Studio Voice transactional container.")
            result = start_transactional_container(
                api_key=ngc_api_key,
                image=settings.image,
                container_name=settings.container_name,
                model_profile=settings.model_profile,
                file_size_limit=settings.file_size_limit,
                force_pull=settings.force_pull,
                username=settings.ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg),
            )
        elif action == "setup_all_transactional":
            logging.info("[NVIDIA Studio Voice Setup] Starting full transactional setup.")
            result = setup_all_transactional(
                api_key=ngc_api_key,
                image=settings.image,
                container_name=settings.container_name,
                model_profile=settings.model_profile,
                file_size_limit=settings.file_size_limit,
                target=settings.target,
                wait_timeout_s=settings.wait_timeout_s,
                force_pull=settings.force_pull,
                username=settings.ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Studio Voice Setup] %s", msg),
            )
        else:
            raise ValueError(f"Unknown setup action: {action}")

        ready = False
        health_line = ""
        if result.ok:
            health_error = check_channel(target=settings.target, timeout_s=5.0)
            ready = health_error is None
            if ready:
                health_line = f"\nHealth: Studio Voice gRPC is reachable at {settings.target}."
            else:
                health_line = f"\nHealth: Studio Voice gRPC is not reachable yet at {settings.target}. Details: {health_error}"
        connection = StudioVoiceConnection(
            target=settings.target,
            model_type=settings.model_type,
            streaming=False,
            ready=ready,
            container_name=settings.container_name,
        )
        prefix = "OK" if result.ok else "ERROR"
        status = f"{prefix}: {result.output}{health_line}\n\n{_settings_summary(settings, settings_source)}"
        return io.NodeOutput(connection, status)


class NvidiaRelightingAdvancedSettings(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaRelightingAdvancedSettings",
            display_name="NVIDIA Relighting Advanced Settings",
            category="NVIDIA Maxine/Setup",
            description="Optional technical Docker/NIM overrides for the Relighting Setup node.",
            search_aliases=["relighting advanced", "nvidia relighting settings", "relighting docker settings"],
            inputs=[
                io.String.Input("image", default=DEFAULT_RELIGHTING_IMAGE),
                io.String.Input("container_name", default=DEFAULT_RELIGHTING_CONTAINER_NAME),
                io.String.Input(
                    "manifest_profile",
                    default="",
                    tooltip="Optional NIM_MANIFEST_PROFILE override. Leave empty to let the Relighting NIM choose.",
                ),
                io.Boolean.Input(
                    "force_pull",
                    default=False,
                    tooltip="When false, existing images/containers are reused. Enable only to refresh the Relighting image.",
                ),
                io.String.Input("target", default=DEFAULT_RELIGHTING_TARGET),
                io.Int.Input("grpc_host_port", default=DEFAULT_RELIGHTING_GRPC_HOST_PORT, min=1, max=65535, step=1),
                io.Int.Input("http_host_port", default=DEFAULT_RELIGHTING_HTTP_HOST_PORT, min=1, max=65535, step=1),
                io.Int.Input("metrics_host_port", default=DEFAULT_RELIGHTING_METRICS_HOST_PORT, min=1, max=65535, step=1),
                io.Float.Input(
                    "wait_timeout_s",
                    default=DEFAULT_RELIGHTING_WAIT_TIMEOUT_S,
                    min=30.0,
                    max=7200.0,
                    step=30.0,
                ),
                io.String.Input(
                    "ngc_username",
                    default=DEFAULT_RELIGHTING_NGC_USERNAME,
                    tooltip="NVIDIA deploy docs use the literal username $oauthtoken for API-key Docker login.",
                ),
            ],
            outputs=[
                RelightingSetupSettingsIO.Output("advanced_settings"),
            ],
        )

    @classmethod
    def execute(
        cls,
        image,
        container_name,
        manifest_profile,
        force_pull,
        target,
        grpc_host_port,
        http_host_port,
        metrics_host_port,
        wait_timeout_s,
        ngc_username,
    ) -> io.NodeOutput:
        settings = _normalize_relighting_settings(
            RelightingSetupSettings(
                image=image,
                container_name=container_name,
                manifest_profile=manifest_profile,
                force_pull=force_pull,
                target=target,
                grpc_host_port=grpc_host_port,
                http_host_port=http_host_port,
                metrics_host_port=metrics_host_port,
                wait_timeout_s=wait_timeout_s,
                ngc_username=ngc_username,
            )
        )
        return io.NodeOutput(settings)


class NvidiaRelightingDockerSetup(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaRelightingDockerSetup",
            display_name="NVIDIA Relighting Docker Setup",
            category="NVIDIA Maxine/Setup",
            description=(
                "User-friendly Windows Docker setup for local NVIDIA Relighting NIM. "
                "The NGC key is used in memory, but saved ComfyUI workflows may retain node input values."
            ),
            search_aliases=["relighting setup", "nvidia relighting nim", "relighting docker", "maxine relight"],
            inputs=[
                io.Combo.Input(
                    "action",
                    options=[
                        "setup_all",
                        "check_docker",
                        "check_gpu",
                        "ngc_login",
                        "pull_relighting",
                        "start_relighting",
                    ],
                    default="setup_all",
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
                RelightingSetupSettingsIO.Input("advanced_settings", optional=True),
            ],
            outputs=[
                RelightingConnectionIO.Output("relighting_connection"),
                io.String.Output("status"),
            ],
            not_idempotent=True,
        )

    @classmethod
    def execute(cls, action, ngc_api_key, advanced_settings=None) -> io.NodeOutput:
        settings_source = "Advanced Settings node" if advanced_settings is not None else "safe defaults"
        settings = _normalize_relighting_settings(advanced_settings)

        if action == "check_docker":
            logging.info("[NVIDIA Relighting Setup] Checking Docker Desktop.")
            result = relighting_docker_info()
        elif action == "check_gpu":
            result = relighting_docker_gpu_check(progress=lambda msg: logging.info("[NVIDIA Relighting Setup] %s", msg))
        elif action == "ngc_login":
            logging.info("[NVIDIA Relighting Setup] Logging into NGC.")
            result = relighting_ngc_login(ngc_api_key, username=settings.ngc_username)
        elif action == "pull_relighting":
            logging.info("[NVIDIA Relighting Setup] Pulling Relighting image: %s", settings.image)
            result = pull_relighting_image(
                ngc_api_key,
                image=settings.image,
                username=settings.ngc_username,
                progress=lambda msg: logging.info("[NVIDIA Relighting Setup] %s", msg),
            )
        elif action == "start_relighting":
            logging.info("[NVIDIA Relighting Setup] Starting Relighting container.")
            result = start_relighting_container(
                api_key=ngc_api_key,
                settings=settings,
                progress=lambda msg: logging.info("[NVIDIA Relighting Setup] %s", msg),
            )
        elif action == "setup_all":
            logging.info("[NVIDIA Relighting Setup] Starting full setup.")
            result = setup_all_relighting(
                api_key=ngc_api_key,
                settings=settings,
                progress=lambda msg: logging.info("[NVIDIA Relighting Setup] %s", msg),
            )
        else:
            raise ValueError(f"Unknown Relighting setup action: {action}")

        ready = False
        health_line = ""
        if result.ok:
            health_error = check_relighting_channel(target=settings.target, timeout_s=5.0)
            ready = health_error is None
            if ready:
                health_line = f"\nHealth: Relighting gRPC is reachable at {settings.target}."
            else:
                health_line = f"\nHealth: Relighting gRPC is not reachable yet at {settings.target}. Details: {health_error}"
        connection = RelightingConnection(
            target=settings.target,
            ready=ready,
            container_name=settings.container_name,
            timeout_s=settings.wait_timeout_s,
            setup_error="" if result.ok else result.output,
        )
        prefix = "OK" if result.ok else "ERROR"
        status = f"{prefix}: {result.output}{health_line}\n\n{_relighting_settings_summary(settings, settings_source)}"
        return io.NodeOutput(connection, status)


class NvidiaRelightingApply(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaRelightingApply",
            display_name="NVIDIA Relighting Apply",
            category="NVIDIA Maxine/Video",
            description="Apply NVIDIA Relighting to a local MP4 file through a locally hosted Relighting NIM.",
            search_aliases=["relighting apply", "nvidia relighting", "maxine relight video", "video relight"],
            inputs=[
                io.String.Input("video_path", default="", tooltip="Local .mp4 path. The first version does not convert MOV/WebM/etc."),
                RelightingConnectionIO.Input("relighting_connection", optional=True),
                io.Combo.Input("hdri_preset", options=list(HDRI_PRESETS), default=HDRI_PRESETS[0]),
                io.Float.Input("foreground_gain", default=1.0, min=0.0, max=3.0, step=0.05),
                io.Float.Input("background_gain", default=1.0, min=0.0, max=3.0, step=0.05),
                io.Float.Input("blur", default=0.0, min=0.0, max=1.0, step=0.05),
                io.Float.Input("specular", default=0.0, min=0.0, max=3.0, step=0.05),
                io.String.Input(
                    "output_path",
                    default="",
                    tooltip="Optional output .mp4 path. Empty saves to ComfyUI output.",
                    advanced=True,
                ),
                io.Float.Input("pan", default=-90.0, min=-180.0, max=180.0, step=1.0, advanced=True),
                io.Float.Input("vertical_fov", default=60.0, min=5.0, max=180.0, step=1.0, advanced=True),
                io.Boolean.Input("autorotate", default=False, advanced=True),
                io.Float.Input("rotation_rate", default=20.0, min=-360.0, max=360.0, step=1.0, advanced=True),
                io.Combo.Input(
                    "background_source",
                    options=list(BACKGROUND_SOURCES),
                    default=BACKGROUND_SOURCES[0],
                    advanced=True,
                ),
                io.String.Input("background_image_path", default="", advanced=True),
                io.String.Input("background_color", default="", tooltip="Optional #RRGGBB or 0xRRGGBB.", advanced=True),
                io.Int.Input("bitrate", default=10000000, min=0, max=200000000, step=1000000, advanced=True),
                io.Int.Input("idr_interval", default=8, min=0, max=300, step=1, advanced=True),
                io.Boolean.Input("lossless", default=False, advanced=True),
                io.Float.Input("timeout_s", default=3600.0, min=30.0, max=14400.0, step=30.0, advanced=True),
            ],
            outputs=[
                io.String.Output("output_video_path"),
                io.String.Output("status"),
            ],
        )

    @classmethod
    def execute(
        cls,
        video_path,
        relighting_connection=None,
        hdri_preset=HDRI_PRESETS[0],
        foreground_gain=1.0,
        background_gain=1.0,
        blur=0.0,
        specular=0.0,
        output_path="",
        pan=-90.0,
        vertical_fov=60.0,
        autorotate=False,
        rotation_rate=20.0,
        background_source=BACKGROUND_SOURCES[0],
        background_image_path="",
        background_color="",
        bitrate=10000000,
        idr_interval=8,
        lossless=False,
        timeout_s=3600.0,
    ) -> io.NodeOutput:
        target = DEFAULT_RELIGHTING_TARGET
        if relighting_connection is not None:
            target = relighting_connection.target
            if not getattr(relighting_connection, "ready", False):
                setup_error = str(getattr(relighting_connection, "setup_error", "") or "").strip()
                if setup_error:
                    raise RuntimeError(
                        "Relighting setup did not complete, so Apply cannot run yet. "
                        "Fix the Docker Setup node first. Setup details:\n"
                        f"{setup_error}"
                    )
                live_error = check_relighting_channel(target=target, timeout_s=5.0)
                if live_error is not None:
                    raise RuntimeError(
                        "Relighting is not ready at "
                        f"{target}. Run NVIDIA Relighting Docker Setup with action setup_all and a valid NGC API key, "
                        f"then check the Setup node's status output. Docker/NIM details: {live_error}"
                    )

        clean_video_path = str(video_path or "").strip().strip('"')
        if not clean_video_path:
            raise ValueError("video_path is empty. Provide a local MP4 file path.")
        clean_output_path = str(output_path or "").strip().strip('"') or _default_output_path(clean_video_path)
        logging.info("[NVIDIA Relighting Apply] Starting relighting for %s.", clean_video_path)
        destination, total_bytes, elapsed = relight_video(
            video_path=clean_video_path,
            output_path=clean_output_path,
            target=target,
            hdri_preset=hdri_preset,
            foreground_gain=foreground_gain,
            background_gain=background_gain,
            blur=blur,
            specular=specular,
            pan=pan,
            vertical_fov=vertical_fov,
            autorotate=autorotate,
            rotation_rate=rotation_rate,
            background_source=background_source,
            background_image_path=str(background_image_path or "").strip().strip('"') or None,
            background_color=background_color,
            bitrate=bitrate,
            idr_interval=idr_interval,
            lossless=lossless,
            timeout_s=timeout_s,
            progress=lambda msg: logging.info("[NVIDIA Relighting Apply] %s", msg),
        )
        status = (
            f"OK: Relighting completed in {elapsed:.1f}s.\n"
            f"Output: {destination}\n"
            f"Bytes received: {total_bytes}\n"
            f"Target: {target}\n"
            f"HDRI preset: {hdri_preset}"
        )
        return io.NodeOutput(str(destination), status)


class NvidiaMaxineExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            NvidiaStudioVoiceAdvancedSettings,
            NvidiaStudioVoiceDockerSetup,
            NvidiaStudioVoiceEnhance,
            NvidiaRelightingAdvancedSettings,
            NvidiaRelightingDockerSetup,
            NvidiaRelightingApply,
        ]


async def comfy_entrypoint() -> NvidiaMaxineExtension:
    return NvidiaMaxineExtension()
