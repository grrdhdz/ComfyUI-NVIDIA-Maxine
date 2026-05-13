from __future__ import annotations

import time
from typing import Iterable, Iterator, Optional

import grpc
import numpy as np

from .audio_utils import decode_wav_bytes, encode_wav_bytes
from .interfaces import studiovoice_pb2, studiovoice_pb2_grpc


MODEL_TYPES = ("48k-hq", "48k-ll", "16k-hq")


def _transactional_requests(wav_bytes: bytes) -> Iterator[studiovoice_pb2.EnhanceAudioRequest]:
    chunk_size = 64 * 1024
    for pos in range(0, len(wav_bytes), chunk_size):
        yield studiovoice_pb2.EnhanceAudioRequest(audio_stream_data=wav_bytes[pos : pos + chunk_size])


def _streaming_requests(
    audio_np: np.ndarray,
    sample_rate: int,
    model_type: str,
) -> Iterator[studiovoice_pb2.EnhanceAudioRequest]:
    input_size_ms = 10 if model_type == "48k-ll" else 6000
    chunk_samples = int(input_size_ms * (sample_rate // 1000))
    pad_length = (chunk_samples - (len(audio_np) % chunk_samples)) % chunk_samples
    if pad_length:
        audio_np = np.pad(audio_np, (0, pad_length), "constant")

    for pos in range(0, len(audio_np), chunk_samples):
        chunk = audio_np[pos : pos + chunk_samples].astype(np.float32, copy=False)
        yield studiovoice_pb2.EnhanceAudioRequest(audio_stream_data=chunk.tobytes())


def enhance_audio(
    audio_np: np.ndarray,
    sample_rate: int,
    target: str = "127.0.0.1:8001",
    model_type: str = "48k-hq",
    streaming: bool = False,
    timeout_s: float = 120.0,
) -> tuple[np.ndarray, int, float]:
    """Run Studio Voice against a local insecure gRPC target."""
    if model_type not in MODEL_TYPES:
        raise ValueError(f"Unsupported Studio Voice model_type: {model_type}")

    start = time.time()
    with grpc.insecure_channel(target) as channel:
        grpc.channel_ready_future(channel).result(timeout=timeout_s)
        stub = studiovoice_pb2_grpc.StudioVoiceStub(channel)
        if streaming:
            requests: Iterable[studiovoice_pb2.EnhanceAudioRequest] = _streaming_requests(
                audio_np=audio_np,
                sample_rate=sample_rate,
                model_type=model_type,
            )
            chunks = [
                np.frombuffer(response.audio_stream_data, dtype=np.float32)
                for response in stub.EnhanceAudio(requests, timeout=timeout_s)
                if response.HasField("audio_stream_data")
            ]
            if not chunks:
                raise RuntimeError("Studio Voice returned no streaming audio chunks.")
            result = np.hstack(chunks).astype(np.float32, copy=False)
            return result, sample_rate, time.time() - start

        wav_bytes = encode_wav_bytes(audio_np, sample_rate)
        responses = stub.EnhanceAudio(_transactional_requests(wav_bytes), timeout=timeout_s)
        output = bytearray()
        for response in responses:
            if response.HasField("audio_stream_data"):
                output.extend(response.audio_stream_data)
        result, result_rate = decode_wav_bytes(bytes(output))
        return result, result_rate, time.time() - start


def check_channel(target: str = "127.0.0.1:8001", timeout_s: float = 5.0) -> Optional[str]:
    try:
        with grpc.insecure_channel(target) as channel:
            grpc.channel_ready_future(channel).result(timeout=timeout_s)
        return None
    except Exception as exc:
        message = str(exc).strip()
        return message or exc.__class__.__name__
