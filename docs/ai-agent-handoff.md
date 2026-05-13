# AI Agent Handoff: ComfyUI NVIDIA Maxine

## Project Summary

This repository implements ComfyUI custom nodes for NVIDIA Maxine NIMs. The
current working scope is Studio Voice, used as an offline recorded-speech
enhancer similar in purpose to Adobe Podcast Enhance Speech.

Primary user goal:

- Run locally on Windows + Docker Desktop.
- Do not use NVIDIA remote inference APIs.
- Let ComfyUI nodes handle Docker login, image pull, container startup, and
  Studio Voice gRPC connection.
- Keep the user workflow simple:

```text
NVIDIA Studio Voice Docker Setup
        |
        | STUDIO_VOICE_CONNECTION
        v
Load Audio -> NVIDIA Studio Voice Enhance -> Save Audio / Preview Audio
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
- `studio_voice/audio_utils.py`: ComfyUI AUDIO conversion helpers.
- `studio_voice/connection.py`: `StudioVoiceConnection` dataclass passed between setup and enhance nodes.
- `studio_voice/interfaces/`: generated NVIDIA Studio Voice gRPC files vendored from `NVIDIA-Maxine/nim-clients`.
- `docs/windows-docker-studio-voice.md`: Windows/Docker operational notes.

The installed Comfy Desktop copy is expected at:

```text
C:\Users\gerhh\Documents\IA\ComfyDesktop\custom_nodes\ComfyUI-NVIDIA-Maxine
```

The development repo is:

```text
C:\Users\gerhh\Documents\IA\ProyectosDesarrolloAgentico\ComfyUI-NVIDIA-Maxine
```

## Nodes

### NVIDIA Studio Voice Docker Setup

Purpose: one user-friendly node that prepares and validates local Studio Voice
NIM.

Inputs and intended defaults:

```text
action:           setup_all_transactional
ngc_api_key:      <user pastes NGC key>
image:            nvcr.io/nim/nvidia/studio-voice:latest
container_name:   studio-voice-nim
model_profile:    <empty>
file_size_limit:  36700160
force_pull:       false
target:           127.0.0.1:8001
model_type:       48k-hq
wait_timeout_s:   900
ngc_username:     $oauthtoken
```

`ngc_username` is advanced and must default to the literal `$oauthtoken`.
NVIDIA Build deploy docs show:

```text
docker login nvcr.io
Username: $oauthtoken
Password: <NGC API key>
```

Important: Do not move fields in the schema casually. ComfyUI workflows can
preserve widget values positionally. A previous insertion of `ngc_username`
before `image` shifted values and corrupted existing workflows. Add new fields
at the end unless there is a migration plan.

Actions:

- `setup_all_transactional`: full setup flow.
- `check_docker`: `docker info`.
- `check_gpu`: validates `--gpus=all` using NVIDIA CUDA sample.
- `ngc_login`: Docker login to `nvcr.io`.
- `pull_studio_voice`: pull Studio Voice NIM image.
- `start_studio_voice_transactional`: start/reuse local transactional container.

Outputs:

- `STUDIO_VOICE_CONNECTION`
- `status` string

The setup node integrates health checking. There is no separate health-check
node in the primary V3 registration.

Idempotency:

- If `studio-voice-nim` is running, reuse it.
- If the container exists but is stopped, `docker start` it.
- If the image exists and `force_pull=false`, do not pull again.
- If the image is absent or `force_pull=true`, login and pull.

### NVIDIA Studio Voice Enhance

Purpose: process recorded ComfyUI `AUDIO` through local Studio Voice NIM.

Inputs:

- Required `audio`.
- Optional `studio_voice_connection`.
- Advanced fallback fields: `target`, `model_type`, `streaming`, `timeout_s`.

If `studio_voice_connection` is connected, it overrides `target/model_type/streaming`.
If the connection says `ready=False`, the node performs a live gRPC check before
failing. This avoids stale false-negative connection objects when the service
became ready after the setup node returned.

Supported sample rates:

- `48k-hq`: input must be 48000 Hz.
- `48k-ll`: input must be 48000 Hz.
- `16k-hq`: input must be 16000 Hz.

Currently the node fails with a clear message when sample rate does not match.
Do not silently resample unless the user explicitly asks for automatic resampling.

## Docker / NIM Behavior

The ComfyUI node communicates with Docker through `docker.exe` using Python
subprocess calls.

Architecture:

```text
ComfyUI node
  -> Python subprocess
  -> docker.exe
  -> Docker Desktop Linux engine
  -> Studio Voice NIM container
  -> local gRPC 127.0.0.1:8001
  -> NVIDIA Studio Voice Enhance node
```

The user wants Windows + Docker Desktop operation. They do not want to work in
an Ubuntu/WSL shell. Docker Desktop may still use its internal WSL2 backend for
GPU support; this is acceptable.

The container is launched in transactional/offline mode for recorded audio:

```text
STREAMING=false
FILE_SIZE_LIMIT=36700160
-p 8000:8000
-p 8001:8001
--gpus all
```

The Studio Voice image name from NVIDIA Build deploy docs is:

```text
nvcr.io/nim/nvidia/studio-voice:latest
```

Before first pull, the user must sign in and accept terms:

```text
https://build.nvidia.com/nvidia/studiovoice/deploy
```

If pull returns access denied after login, likely causes are:

- Studio Voice NIM terms not accepted.
- NGC API key missing `NGC Catalog` service.
- NGC account lacks access to this NIM.
- API key was pasted incorrectly.

## Progress Logging

`docker pull` can be long and Docker Desktop may not show partial image progress.
The current implementation uses streaming subprocess output for pull and logs
lines to ComfyUI logs with:

```text
[NVIDIA Studio Voice Setup]
```

If changing Docker code, preserve this behavior. The user specifically requested
download progress in Comfy logs.

## Security / Secrets

The NGC API key is accepted in the setup node and passed to `docker login` via
stdin.

Rules:

- Do not print the API key.
- Do not write the API key to files.
- Do not include the API key in commits.
- Warn that saved ComfyUI workflows may retain widget values.
- Prefer leaving `ngc_api_key` empty and launching ComfyUI with `NGC_API_KEY` if
  the user wants better hygiene.

The container currently receives `NGC_API_KEY` as an environment variable during
`docker run`, because NIM startup may need it to fetch/cache resources.

## Known Environment Facts

Observed machine:

- Windows.
- Docker Desktop 29.4.0 Linux engine.
- Docker Desktop WSL2 backend enabled.
- NVIDIA GeForce RTX 5060 Ti, 16 GB VRAM.
- Docker `--gpus=all` was validated with `nvcr.io/nvidia/k8s/cuda-sample:nbody`.

Important caveat:

NVIDIA's Studio Voice support matrix has broad RTX Blackwell/Ada/Ampere/Turing
language but historically explicit rows may not list RTX 5060 Ti. If NIM logs
show profile selection errors such as `NIMProfileIDNotFound`, the Comfy nodes
may be correct while the NIM profile/GPU combo is unsupported or requires a
specific `NIM_MODEL_PROFILE`.

## Development Workflow

When editing:

1. Modify files in this repo.
2. Validate V3 entrypoint with Comfy Desktop Python and Comfy core on path.
3. Copy changed files to Comfy Desktop custom_nodes.
4. Restart ComfyUI to test actual UI registration.

Useful validation command pattern:

```powershell
C:\Users\gerhh\Documents\IA\ComfyDesktop\.venv\Scripts\python.exe -c "import asyncio, sys; sys.path.insert(0, r'C:\Users\gerhh\AppData\Local\Programs\ComfyUI\resources\ComfyUI'); sys.path.insert(0, r'C:\Users\gerhh\Documents\IA\ProyectosDesarrolloAgentico\ComfyUI-NVIDIA-Maxine'); import nodes; ext=asyncio.run(nodes.comfy_entrypoint()); lst=asyncio.run(ext.get_node_list()); print([n.GET_SCHEMA().display_name for n in lst])"
```

Expected:

```text
['NVIDIA Studio Voice Docker Setup', 'NVIDIA Studio Voice Enhance']
```

When copying to Comfy Desktop, only copy project files, not
`nim-clients-upstream/`.

## Git State

Initial snapshot:

```text
commit: 40bd2cb feat: add ComfyUI Studio Voice NIM nodes
tag:    snapshot-2026-05-13-studio-voice-nim-v1
```

`nim-clients-upstream/` is ignored and should remain untracked. It was only used
as a reference clone to vendor the generated Studio Voice proto files.

## Future Work

Likely next steps:

- Add automatic optional resampling node/setting if the user wants it.
- Add container logs/status output in the setup node after container start.
- Add support for other NVIDIA Maxine NIMs from `nim-clients`.
- Add a UX wrapper or example workflow JSON once the Studio Voice flow is stable.

Do not add an artificial Studio Voice "intensity" parameter unless the user
approves a dry/wet local mix. The public Studio Voice proto currently transports
only audio bytes and does not expose a native effect-intensity field.

