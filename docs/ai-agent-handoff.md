# AI Agent Handoff: ComfyUI NVIDIA Maxine

## Project Summary

This repository implements ComfyUI custom nodes for NVIDIA Studio Voice NIM.
The supported workflow is recorded-speech enhancement, similar in purpose to
Adobe Podcast Enhance Speech, running locally through Docker Desktop.

Primary user goals:

- Run locally on Windows + Docker Desktop.
- Do not use NVIDIA remote inference APIs.
- Let ComfyUI nodes handle Docker login, image pull, container startup, health
  checks, and Studio Voice gRPC connection.
- Keep the normal workflow simple:

```text
NVIDIA Studio Voice Docker Setup
        |
        | STUDIO_VOICE_CONNECTION
        v
Load Audio -> NVIDIA Studio Voice Enhance -> Save Audio / Preview Audio
```

Advanced overrides are intentionally separated:

```text
NVIDIA Studio Voice Advanced Settings -> NVIDIA Studio Voice Docker Setup
                                                |
                                                v
Load Audio -----------------------> NVIDIA Studio Voice Enhance -> Save Audio
```

## Current Implementation

The package is a ComfyUI V3 custom node package using:

- `comfy_api.latest`
- `io.ComfyNode`
- `define_schema()`
- `execute()` as a classmethod
- `io.NodeOutput`
- `comfy_entrypoint()` returning a `ComfyExtension`

Do not reintroduce legacy `NODE_CLASS_MAPPINGS` unless there is a concrete
compatibility reason. The user explicitly requested the latest ComfyUI node API.

Main files:

- `nodes.py`: V3 node definitions and entrypoint.
- `studio_voice/docker_utils.py`: Docker Desktop / NGC / NIM lifecycle helpers.
- `studio_voice/client.py`: Studio Voice gRPC client.
- `studio_voice/audio_utils.py`: ComfyUI AUDIO conversion and resampling helpers.
- `studio_voice/connection.py`: `StudioVoiceConnection` and
  `StudioVoiceSetupSettings` dataclasses.
- `studio_voice/interfaces/`: generated NVIDIA Studio Voice gRPC files vendored
  from `NVIDIA-Maxine/nim-clients`.
- `requirements.txt`: Python dependencies expected to be installed into the same
  environment that runs ComfyUI.
- `docs/installation.md`: clone/install instructions for other ComfyUI
  installations.
- `docs/windows-docker-studio-voice.md`: Windows/Docker operational notes.

## Nodes

### NVIDIA Studio Voice Advanced Settings

Purpose: optional technical override node for users who need full Docker/NIM
control. This keeps the main setup node user-friendly.

Output:

- `STUDIO_VOICE_SETUP_SETTINGS`

Inputs:

- `image`
- `container_name`
- `model_profile`
- `file_size_limit`
- `force_pull`
- `target`
- `wait_timeout_s`
- `ngc_username`

Important defaults:

```text
image:            nvcr.io/nim/nvidia/studio-voice:latest
container_name:   studio-voice-nim
model_profile:    <auto>
file_size_limit:  36700160
force_pull:       false
target:           127.0.0.1:8001
model_type:       48k-hq
wait_timeout_s:   900
ngc_username:     $oauthtoken
```

### NVIDIA Studio Voice Docker Setup

Purpose: user-friendly node that prepares and validates local Studio Voice NIM.

Visible inputs:

```text
action
ngc_api_key
advanced_settings: optional STUDIO_VOICE_SETUP_SETTINGS connection
```

Actions:

- `setup_all_transactional`: normal path; checks Docker/GPU, logs into NGC,
  pulls/reuses image, starts/reuses container, waits for gRPC.
- `check_docker`
- `check_gpu`
- `ngc_login`
- `pull_studio_voice`
- `start_studio_voice_transactional`

Outputs:

- `STUDIO_VOICE_CONNECTION`
- `status`

Docker behavior:

- Reuses an existing running `studio-voice-nim`.
- Starts it if it exists but is stopped.
- Recreates it if it uses old/conflicting host ports.
- Maps NIM HTTP to host `18000` to avoid Comfy Desktop's common `8000`.
- Maps gRPC to host `8001`.

### NVIDIA Studio Voice Enhance

Purpose: process recorded ComfyUI `AUDIO` through local Studio Voice NIM.

Visible inputs:

- `audio`
- `studio_voice_connection`

Output:

- `enhanced_audio`

The node always uses `48k-hq` internally and automatically resamples source
audio to `48000 Hz` before calling Studio Voice. Do not add a visible model type
selector unless the user explicitly asks for it.

## Docker Communication

The ComfyUI node communicates with Docker through `docker.exe` using Python
`subprocess`. Docker Desktop can use WSL2 internally, but users should not need
to open WSL or run Linux shell commands.

Studio Voice setup flow:

```text
ComfyUI node
  -> docker info
  -> docker run --rm --gpus=all nvcr.io/nvidia/k8s/cuda-sample:nbody ...
  -> docker login nvcr.io --username $oauthtoken --password-stdin
  -> docker pull nvcr.io/nim/nvidia/studio-voice:latest
  -> docker create/start studio-voice-nim
  -> gRPC health/readiness check at 127.0.0.1:8001
```

During long pulls, logs are emitted to ComfyUI with aggregate progress and
heartbeat messages. The implementation uses Docker CLI output parsing, not the
Python Docker SDK.

## Security Notes

- NGC API keys are used in memory for `docker login` and NIM startup.
- Warn that saved ComfyUI workflows may retain widget values.
- Prefer leaving `ngc_api_key` empty and launching ComfyUI with `NGC_API_KEY` if
  the user wants to avoid saving keys in workflow JSON.
- Do not echo full API keys in logs, docs, or responses.

## Validation

Useful checks:

```powershell
python -m py_compile nodes.py studio_voice\audio_utils.py studio_voice\client.py studio_voice\docker_utils.py
```

Comfy Desktop registration check:

```powershell
C:\Users\gerhh\Documents\IA\ComfyDesktop\.venv\Scripts\python.exe -c "import asyncio, sys; sys.path.insert(0, r'C:\Users\gerhh\AppData\Local\Programs\ComfyUI\resources\ComfyUI'); sys.path.insert(0, r'C:\Users\gerhh\Documents\IA\ProyectosDesarrolloAgentico\ComfyUI-NVIDIA-Maxine'); import nodes; ext=asyncio.run(nodes.comfy_entrypoint()); lst=asyncio.run(ext.get_node_list()); print([n.GET_SCHEMA().display_name for n in lst])"
```

Expected nodes:

```text
['NVIDIA Studio Voice Advanced Settings', 'NVIDIA Studio Voice Docker Setup', 'NVIDIA Studio Voice Enhance']
```
