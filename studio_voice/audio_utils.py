from __future__ import annotations

import io
from typing import Tuple

import numpy as np
import torch


def expected_sample_rate(model_type: str) -> int:
    if model_type == "16k-hq":
        return 16000
    return 48000


def comfy_audio_to_numpy(audio: dict) -> Tuple[np.ndarray, int]:
    """Return mono float32 numpy audio and sample rate from a ComfyUI AUDIO dict."""
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("Expected ComfyUI AUDIO dict with waveform and sample_rate.")

    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    if not isinstance(waveform, torch.Tensor):
        raise ValueError("AUDIO waveform must be a torch.Tensor.")

    wav = waveform.detach().cpu().float()
    if wav.ndim == 3:
        wav = wav[0]
    if wav.ndim == 2:
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0)
        else:
            wav = wav[0]
    if wav.ndim != 1:
        raise ValueError(f"Unsupported AUDIO waveform shape: {tuple(waveform.shape)}")

    return wav.contiguous().numpy().astype(np.float32, copy=False), sample_rate


def numpy_to_comfy_audio(audio_np: np.ndarray, sample_rate: int) -> dict:
    audio_np = np.asarray(audio_np, dtype=np.float32)
    if audio_np.ndim == 1:
        waveform = torch.from_numpy(audio_np[None, None, :].copy())
    elif audio_np.ndim == 2:
        # soundfile returns [samples, channels]; ComfyUI expects [batch, channels, samples].
        waveform = torch.from_numpy(audio_np.T[None, :, :].copy())
    else:
        raise ValueError(f"Unsupported decoded audio shape: {audio_np.shape}")
    return {"waveform": waveform, "sample_rate": int(sample_rate)}


def encode_wav_bytes(audio_np: np.ndarray, sample_rate: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, audio_np, int(sample_rate), format="WAV", subtype="FLOAT")
    return buf.getvalue()


def decode_wav_bytes(data: bytes) -> Tuple[np.ndarray, int]:
    import soundfile as sf

    if not data:
        raise ValueError("Studio Voice returned an empty audio payload.")
    audio_np, sample_rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    return audio_np, int(sample_rate)

