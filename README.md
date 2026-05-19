# ComfyUI NVIDIA Maxine

Custom nodes for running NVIDIA Maxine NIMs from ComfyUI. The first stable
workflow is Studio Voice for recorded-speech enhancement.

## Installation

### 1. Install Docker Desktop

1. Install Docker Desktop for Windows from the official Docker documentation:
   https://docs.docker.com/desktop/setup/install/windows-install/
2. During setup, use the WSL 2 backend. Docker documents GPU support on Windows
   as available through the WSL2 backend:
   https://docs.docker.com/desktop/features/gpu/
3. Start Docker Desktop before running the setup node in ComfyUI.
4. In Docker Desktop, confirm that `Settings -> General -> Use the WSL 2 based
   engine` is enabled.

You do not need to work inside WSL manually. These nodes call `docker.exe` from
Windows/ComfyUI and Docker Desktop handles the Linux backend internally.

### 2. Get an NVIDIA NGC API Key

Studio Voice is distributed as an NVIDIA NIM image from NGC. NVIDIA's Studio
Voice NIM getting-started page documents the local Docker image and NGC login
flow:

https://docs.nvidia.com/nim/maxine/studio-voice/latest/getting-started.html

To prepare access:

1. Sign in to NVIDIA/NGC.
2. Open the Studio Voice NIM page and accept the terms if prompted:
   https://build.nvidia.com/nvidia/studiovoice/deploy
3. Create an NGC Personal API key from NVIDIA's NGC API Keys page:
   https://org.ngc.nvidia.com/setup/api-keys
4. When creating the Personal API key, include at least the `NGC Catalog`
   service. NVIDIA documents this requirement in the Studio Voice NIM
   getting-started page.
5. Keep the key private. Saved ComfyUI workflows can retain widget values, so do
   not share workflows that contain a real `ngc_api_key`.

The Docker username is the literal value:

```text
$oauthtoken
```

The password is your NGC API key. The normal setup node already uses
`$oauthtoken` internally, so most users only paste the API key.

### 3. Install This Custom Node

Clone this repository into ComfyUI's `custom_nodes` folder and install the
Python dependencies with the same Python environment that runs ComfyUI:

```powershell
cd C:\path\to\ComfyUI\custom_nodes
git clone https://github.com/grrdhdz/ComfyUI-NVIDIA-Maxine.git
cd ComfyUI-NVIDIA-Maxine
C:\path\to\ComfyUI\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For ComfyUI portable builds, replace the Python path with the portable embedded
Python executable. For Comfy Desktop, use that installation's `.venv` Python.

Restart ComfyUI after installing. The normal dependency file is
`requirements.txt`; there is no `requirements.py`.

Runtime requirements:

- ComfyUI with the V3 custom node API. Development has been validated against
  ComfyUI `0.21.0`.
- Docker Desktop on Windows with the WSL2 engine enabled.
- NVIDIA GPU access from Docker.
- NGC Personal API key with access to the NVIDIA Studio Voice NIM image.

More detailed setup notes are in `docs/installation.md` and
`docs/windows-docker-studio-voice.md`.

## Example Workflow

An example ComfyUI workflow is included at:

```text
workflows/nvidia_studio_voice_enhance.json
```

Import it in ComfyUI with `Workflow -> Open` or by dragging the JSON file into
the ComfyUI canvas. The workflow's `ngc_api_key` field is intentionally blank.
Paste your own key into `NVIDIA Studio Voice Docker Setup`, or leave the field
blank and launch ComfyUI with `NGC_API_KEY` set in the environment.

The example workflow uses this shape:

```text
NVIDIA Studio Voice Docker Setup -> NVIDIA Studio Voice Enhance
Load Audio -----------------------> NVIDIA Studio Voice Enhance -> Preview/Save Audio
```

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
progress to ComfyUI logs. It parses Docker CLI output and reports known byte
percentage, downloaded/pulled layer counts, and periodic heartbeats while
Docker is still working.
