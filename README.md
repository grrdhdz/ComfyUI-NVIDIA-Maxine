# ComfyUI NVIDIA Maxine

Custom nodes for running NVIDIA Maxine NIMs from ComfyUI. Phase 1 focuses on
Studio Voice as an offline speech enhancement node for recorded audio.

## Studio Voice Workflow

Simple mode uses ComfyUI's built-in audio nodes plus the Studio Voice setup
connection:

```text
NVIDIA Studio Voice Docker Setup
    |
    v
Load Audio -> NVIDIA Studio Voice Enhance -> Save Audio
```

Advanced mode adds one optional settings node before setup:

```text
NVIDIA Studio Voice Advanced Settings -> NVIDIA Studio Voice Docker Setup
                                                |
                                                v
Load Audio -----------------------> NVIDIA Studio Voice Enhance -> Save Audio
```

The node calls a locally hosted Studio Voice NIM over gRPC at
`127.0.0.1:8001` by default. It does not call NVIDIA's remote preview API and
does not accept an API key inside ComfyUI.

Studio Voice's optional HTTP port is mapped to host port `18000` instead of
`8000`, because Comfy Desktop commonly uses host port `8000` for its own UI.

## Friendly Setup Node

Use `NVIDIA Studio Voice Docker Setup` from ComfyUI to prepare the local NIM.
The normal action is:

```text
setup_all_transactional
```

That single action runs Docker detection, GPU validation, NGC login, image pull,
container start, and waits for the local gRPC endpoint.

The setup node exposes only the NGC key and setup action in the normal UI. It
uses safe internal defaults for image, container name, target, model type, file
size limit, timeout, and NGC username.

The setup node outputs `STUDIO_VOICE_CONNECTION`. Connect it to
`NVIDIA Studio Voice Enhance` so the working node receives the verified target
and model settings.

The setup node includes the health check in its status output. There is no
separate health-check node in the primary V3 registration.

By default the setup is idempotent:

- If the container is already running, it reuses it.
- If the container exists but is stopped, it starts it.
- If the image already exists, it does not pull again.
- If an older `studio-voice-nim` container maps host port `8000`, setup
  recreates it with NIM HTTP on host port `18000` to avoid blocking Comfy
  Desktop.
- Connect `NVIDIA Studio Voice Advanced Settings` only when you intentionally
  need to override technical Docker/NIM values such as `force_pull`, image,
  target, model type, or timeouts.

Advanced step-by-step actions are also available:

1. `check_docker`
2. `check_gpu`
3. `ngc_login`
4. `pull_studio_voice`
5. `start_studio_voice_transactional`

Paste the NGC API key into `ngc_api_key`, or leave it empty if ComfyUI was
started with `NGC_API_KEY` already set. The node uses the key in memory for
Docker login and NIM startup, and does not write it to project files. Be aware
that ComfyUI workflows can store node input values when saved.

For Docker login, NVIDIA's deploy page uses:

```text
Username: $oauthtoken
Password: <NGC API key>
```

The advanced settings node exposes `ngc_username` and defaults it to the
literal `$oauthtoken`. This is not your NVIDIA account email.

Before the first pull, sign in at NVIDIA Build and accept the Studio Voice NIM
Terms of Use:

https://build.nvidia.com/nvidia/studiovoice/deploy

If `docker pull` reports access denied after a successful login, the most common
causes are missing Terms acceptance, a key without `NGC Catalog`, or an account
without access to this downloadable NIM.

## Controls

The normal `Enhance` flow needs only `audio` and `studio_voice_connection`.
It always uses Studio Voice `48k-hq` and automatically resamples incoming audio
to `48000 Hz` before calling the local NIM.

Internal fallback values remain fixed for direct/manual use:

- `target`: local gRPC target, usually `127.0.0.1:8001`.
- `streaming`: off by default. Use `false` for recorded-file enhancement.
- `timeout_s`: gRPC timeout.

Studio Voice's public proto only exposes audio bytes. It does not expose a
native intensity control, so this package intentionally does not add a dry/wet
or artificial intensity slider.

## Sample Rates

The package uses `48k-hq` by default and prepares audio at `48000 Hz`
automatically. Common inputs such as 44100 Hz phone or messaging-app audio are
resampled inside `NVIDIA Studio Voice Enhance`.

## Local NIM Requirement

Studio Voice must already be running locally in Docker Desktop. On Windows,
Docker GPU support requires Docker Desktop's WSL2 backend, but all commands and
ComfyUI operation can still be done from Windows/PowerShell.

See `docs/windows-docker-studio-voice.md` for setup notes.

## Docker Pull Logs

During long Studio Voice image downloads, the setup node writes aggregate pull
progress to ComfyUI logs. It tries Docker Engine API progress first when the
Python Docker SDK is available, then falls back to Docker CLI output parsing.
Logs include known byte percentage, downloaded/pulled layer counts, and
periodic heartbeats while Docker is still working.
