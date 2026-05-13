from __future__ import annotations

import math
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import grpc


INTERFACES_PATH = Path(__file__).resolve().parent / "interfaces"
if str(INTERFACES_PATH) not in sys.path:
    sys.path.insert(0, str(INTERFACES_PATH))

from nvidia.ai4m.relighting.v1 import relighting_pb2, relighting_pb2_grpc  # noqa: E402
from nvidia.ai4m.video.v1 import video_pb2  # noqa: E402


DATA_CHUNK_SIZE = 64 * 1024
DEFAULT_TARGET = "127.0.0.1:8101"
DEFAULT_BITRATE_BPS = 10_000_000
DEFAULT_IDR_INTERVAL = 8
HDRI_PRESETS = (
    "0 Lounge",
    "1 Cobblestone Street Night",
    "2 Glasshouse Interior",
    "3 Little Paris Eiffel Tower",
    "4 Wooden Studio",
)
BACKGROUND_SOURCES = (
    "0 Source Video",
    "1 Custom Image",
    "2 HDR Projection",
)

ProgressCallback = Callable[[str], None]


def check_channel(target: str = DEFAULT_TARGET, timeout_s: float = 5.0) -> str | None:
    options = _channel_options()
    try:
        with grpc.insecure_channel(target, options=options) as channel:
            grpc.channel_ready_future(channel).result(timeout=float(timeout_s))
        return None
    except Exception as exc:  # noqa: BLE001 - surface gRPC readiness details to Comfy logs/status.
        return f"{exc.__class__.__name__}: {exc}"


def relight_video(
    *,
    video_path: str | Path,
    output_path: str | Path,
    target: str = DEFAULT_TARGET,
    hdri_preset: str = HDRI_PRESETS[0],
    foreground_gain: float = 1.0,
    background_gain: float = 1.0,
    blur: float = 0.0,
    specular: float = 0.0,
    pan: float = -90.0,
    vertical_fov: float = 60.0,
    autorotate: bool = False,
    rotation_rate: float = 20.0,
    background_source: str = BACKGROUND_SOURCES[0],
    background_image_path: str | Path | None = None,
    background_color: str = "",
    bitrate: int = DEFAULT_BITRATE_BPS,
    idr_interval: int = DEFAULT_IDR_INTERVAL,
    lossless: bool = False,
    timeout_s: float = 3600.0,
    progress: ProgressCallback | None = None,
) -> tuple[Path, int, float]:
    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(f"Relighting input video does not exist: {source}")
    if source.suffix.lower() != ".mp4":
        raise ValueError(
            "NVIDIA Relighting v1 expects an MP4/H.264 input file. "
            f"Received {source.suffix or '<no extension>'}; convert it to .mp4 before this node."
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    bg_path = Path(background_image_path) if background_image_path else None
    if _background_source_id(background_source) == relighting_pb2.BACKGROUND_SOURCE_FROM_IMAGE:
        if bg_path is None or not str(bg_path).strip():
            raise ValueError("background_source is Custom Image, but background_image_path is empty.")
        if not bg_path.exists():
            raise FileNotFoundError(f"Relighting background image does not exist: {bg_path}")

    config = _build_relight_config(
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
        background_color=background_color,
        bitrate=bitrate,
        idr_interval=idr_interval,
        lossless=lossless,
    )
    started = time.time()
    _emit(progress, f"Opening local Relighting gRPC channel at {target}.")
    with grpc.insecure_channel(target, options=_channel_options()) as channel:
        grpc.channel_ready_future(channel).result(timeout=float(min(timeout_s, 30.0)))
        stub = relighting_pb2_grpc.VideoRelightingServiceStub(channel)
        responses = stub.Relight(
            _generate_requests(source, config, bg_path=bg_path),
            timeout=float(timeout_s),
        )
        total_bytes = _write_response_to_file(responses, destination, progress=progress)
    elapsed = time.time() - started
    _emit(progress, f"Relighting completed in {elapsed:.1f}s. Output: {destination}")
    return destination, total_bytes, elapsed


def _channel_options() -> list[tuple[str, int | bool]]:
    return [
        ("grpc.max_send_message_length", 100 * 1024 * 1024),
        ("grpc.max_receive_message_length", 100 * 1024 * 1024),
        ("grpc.keepalive_time_ms", 10_000),
        ("grpc.keepalive_timeout_ms", 60_000),
        ("grpc.keepalive_permit_without_calls", True),
        ("grpc.http2.max_pings_without_data", 0),
    ]


def _build_video_encoding(*, bitrate: int, idr_interval: int, lossless: bool) -> video_pb2.VideoEncoding:
    encoding = video_pb2.VideoEncoding()
    if lossless:
        encoding.lossless = True
        return encoding
    bitrate_mbps = max(1, round(max(0, int(bitrate)) / 1_000_000))
    encoding.lossy.CopyFrom(video_pb2.LossyEncoding(bitrate_mbps=bitrate_mbps, idr_interval=max(0, int(idr_interval))))
    return encoding


def _build_relight_config(
    *,
    hdri_preset: str,
    foreground_gain: float,
    background_gain: float,
    blur: float,
    specular: float,
    pan: float,
    vertical_fov: float,
    autorotate: bool,
    rotation_rate: float,
    background_source: str,
    background_color: str,
    bitrate: int,
    idr_interval: int,
    lossless: bool,
) -> relighting_pb2.RelightConfig:
    config = relighting_pb2.RelightConfig()
    config.hdri_preset_id = _leading_int(hdri_preset, default=0)
    config.angle_pan_radians = math.radians(float(pan))
    config.angle_v_fov_radians = math.radians(float(vertical_fov))
    config.output_video_encoding.CopyFrom(
        _build_video_encoding(bitrate=bitrate, idr_interval=idr_interval, lossless=lossless)
    )
    config.background_source = _background_source_id(background_source)
    color = _parse_background_color(background_color)
    if color is not None:
        config.background_color = color
    config.background_image_type = relighting_pb2.IMAGE_TYPE_BACKGROUND
    config.foreground_gain = float(foreground_gain)
    config.background_gain = float(background_gain)
    config.blur_strength = float(blur)
    config.specular = float(specular)
    config.autorotate = bool(autorotate)
    config.rotation_rate = math.radians(float(rotation_rate))
    return config


def _generate_requests(
    video_path: Path,
    config: relighting_pb2.RelightConfig,
    *,
    bg_path: Path | None,
) -> Iterator[relighting_pb2.RelightRequest]:
    yield relighting_pb2.RelightRequest(config=config)
    if bg_path is not None:
        with bg_path.open("rb") as image_file:
            while chunk := image_file.read(DATA_CHUNK_SIZE):
                yield relighting_pb2.RelightRequest(
                    image_data=relighting_pb2.ImageData(
                        image_type=relighting_pb2.IMAGE_TYPE_BACKGROUND,
                        data=chunk,
                    )
                )
    with video_path.open("rb") as video_file:
        while chunk := video_file.read(DATA_CHUNK_SIZE):
            yield relighting_pb2.RelightRequest(video_data=chunk)


def _write_response_to_file(
    responses: Iterator[relighting_pb2.RelightResponse],
    output_path: Path,
    *,
    progress: ProgressCallback | None,
) -> int:
    total_bytes = 0
    chunk_count = 0
    first_chunk_time: float | None = None
    last_emit = 0.0
    start = time.time()

    with output_path.open("wb") as output:
        for response in responses:
            if response.HasField("image_upload_ack"):
                ack = response.image_upload_ack
                _emit(progress, f"Relighting accepted image upload: {ack.size_bytes / 1024:.1f} KB.")
                continue
            if response.HasField("progress"):
                frames = response.progress.frames_processed
                if response.progress.HasField("total_frames") and response.progress.total_frames > 0:
                    total = response.progress.total_frames
                    _emit(progress, f"Relighting progress: {100.0 * frames / total:.1f}% ({frames}/{total} frames).")
                else:
                    _emit(progress, f"Relighting progress: frame {frames}.")
                continue
            if response.HasField("keep_alive"):
                now = time.time()
                if now - last_emit >= 30.0:
                    _emit(progress, f"Relighting is still processing: elapsed {now - start:.0f}s.")
                    last_emit = now
                continue
            if not response.HasField("video_data"):
                continue

            if first_chunk_time is None:
                first_chunk_time = time.time()
                _emit(progress, f"Relighting server started returning video after {first_chunk_time - start:.1f}s.")
            output.write(response.video_data)
            chunk_count += 1
            total_bytes += len(response.video_data)
            now = time.time()
            if now - last_emit >= 5.0:
                mb = total_bytes / (1024 * 1024)
                _emit(progress, f"Receiving relit video: {chunk_count} chunks, {mb:.2f} MB.")
                last_emit = now

    if total_bytes <= 0:
        raise RuntimeError("Relighting completed without returning video bytes.")
    return total_bytes


def _leading_int(value: str, *, default: int) -> int:
    text = str(value).strip()
    first = text.split(maxsplit=1)[0] if text else ""
    try:
        return int(first)
    except ValueError:
        return default


def _background_source_id(value: str) -> int:
    index = _leading_int(value, default=0)
    if index == 1:
        return relighting_pb2.BACKGROUND_SOURCE_FROM_IMAGE
    if index == 2:
        return relighting_pb2.BACKGROUND_SOURCE_FROM_HDR
    return relighting_pb2.BACKGROUND_SOURCE_UNSPECIFIED


def _parse_background_color(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("#"):
        text = text[1:]
    if text.lower().startswith("0x"):
        text = text[2:]
    if len(text) != 6:
        raise ValueError("background_color must be empty, #RRGGBB, or 0xRRGGBB.")
    try:
        return int(text, 16)
    except ValueError as exc:
        raise ValueError("background_color must be empty, #RRGGBB, or 0xRRGGBB.") from exc


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)
