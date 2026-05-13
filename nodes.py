from __future__ import annotations

import logging

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
    from .studio_voice.client import MODEL_TYPES, check_channel, enhance_audio
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
    from studio_voice.client import MODEL_TYPES, check_channel, enhance_audio
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


StudioVoiceConnectionIO = io.Custom("STUDIO_VOICE_CONNECTION")
StudioVoiceSetupSettingsIO = io.Custom("STUDIO_VOICE_SETUP_SETTINGS")


def _normalize_setup_settings(settings: StudioVoiceSetupSettings | None) -> StudioVoiceSetupSettings:
    if not isinstance(settings, StudioVoiceSetupSettings):
        settings = StudioVoiceSetupSettings()

    model_type = settings.model_type if settings.model_type in MODEL_TYPES else DEFAULT_MODEL_TYPE
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
        model_type=model_type,
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
                io.Combo.Input("model_type", options=list(MODEL_TYPES), default=DEFAULT_MODEL_TYPE),
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
        model_type,
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
                model_type=model_type,
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
                io.String.Input("target", default=DEFAULT_TARGET, advanced=True),
                io.Combo.Input("model_type", options=list(MODEL_TYPES), default=DEFAULT_MODEL_TYPE, advanced=True),
                io.Boolean.Input("streaming", default=False, advanced=True),
                io.Float.Input("timeout_s", default=120.0, min=1.0, max=3600.0, step=1.0, advanced=True),
            ],
            outputs=[
                io.Audio.Output("enhanced_audio"),
            ],
        )

    @classmethod
    def execute(
        cls,
        audio,
        studio_voice_connection=None,
        target=DEFAULT_TARGET,
        model_type=DEFAULT_MODEL_TYPE,
        streaming=False,
        timeout_s=120.0,
    ) -> io.NodeOutput:
        if studio_voice_connection is not None:
            target = studio_voice_connection.target
            model_type = studio_voice_connection.model_type
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


class NvidiaStudioVoicePrepareAudio(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NvidiaStudioVoicePrepareAudio",
            display_name="NVIDIA Studio Voice Prepare Audio",
            category="NVIDIA Maxine/Audio",
            description="Prepare recorded audio for Studio Voice by resampling it to the selected model sample rate.",
            search_aliases=["studio voice resample", "studio voice prepare", "audio resample", "48k audio"],
            inputs=[
                io.Audio.Input("audio"),
                StudioVoiceConnectionIO.Input("studio_voice_connection", optional=True),
                io.Combo.Input("model_type", options=list(MODEL_TYPES), default=DEFAULT_MODEL_TYPE, advanced=True),
            ],
            outputs=[
                io.Audio.Output("audio"),
                io.String.Output("status"),
            ],
        )

    @classmethod
    def execute(
        cls,
        audio,
        studio_voice_connection=None,
        model_type=DEFAULT_MODEL_TYPE,
    ) -> io.NodeOutput:
        if studio_voice_connection is not None:
            model_type = studio_voice_connection.model_type
        if model_type not in MODEL_TYPES:
            model_type = DEFAULT_MODEL_TYPE

        target_sample_rate = expected_sample_rate(model_type)
        prepared_audio, source_sample_rate, changed = resample_comfy_audio(audio, target_sample_rate)
        if changed:
            status = (
                "Resampled audio for Studio Voice: "
                f"{source_sample_rate} Hz -> {target_sample_rate} Hz "
                f"for model_type {model_type}."
            )
        else:
            status = f"Audio already matches Studio Voice model_type {model_type}: {target_sample_rate} Hz."
        return io.NodeOutput(prepared_audio, status)


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


class NvidiaMaxineExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            NvidiaStudioVoiceAdvancedSettings,
            NvidiaStudioVoiceDockerSetup,
            NvidiaStudioVoicePrepareAudio,
            NvidiaStudioVoiceEnhance,
        ]


async def comfy_entrypoint() -> NvidiaMaxineExtension:
    return NvidiaMaxineExtension()
