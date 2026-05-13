# Windows + Docker Desktop Studio Voice Notes

This project is intended to run from Windows and Comfy Desktop. Do not develop
inside an Ubuntu/WSL workspace. Docker Desktop may still need its WSL2 backend
internally because Docker documents NVIDIA GPU support on Windows as WSL2-only.

## Validate Docker GPU Support

From PowerShell:

```powershell
docker info
docker run --rm --gpus=all nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -gpu -benchmark
```

If `docker info` cannot connect, start Docker Desktop. If `--gpus=all` fails,
enable Docker Desktop's WSL2 based engine and update WSL:

```powershell
wsl --update
```

Then in Docker Desktop:

```text
Settings -> General -> Use the WSL 2 based engine
```

Docker Desktop GPU support on Windows is documented as WSL2-backend only. This
does not require using an Ubuntu terminal or moving the project into WSL; it only
means Docker Desktop runs Linux containers through its internal WSL2 backend.

## NGC Policy

The nodes do not use NVIDIA remote inference. An NGC API key may still be
required for the initial Docker login or pulling the Studio Voice NIM image.
After the image/model is cached locally, ComfyUI calls only the local gRPC
service.

Before the first pull, sign in and accept the Studio Voice Terms of Use:

```text
https://build.nvidia.com/nvidia/studiovoice/deploy
```

The deploy page lists the image used by this package:

```text
nvcr.io/nim/nvidia/studio-voice:latest
```

You can do this from ComfyUI with `NVIDIA Studio Voice Docker Setup`:

```text
check_docker -> check_gpu -> ngc_login -> pull_studio_voice -> start_studio_voice_transactional
```

The setup node does not write the key to disk, but saved ComfyUI workflows may
retain input values. For maximum hygiene, set `NGC_API_KEY` before launching
ComfyUI and leave the node's `ngc_api_key` field empty.

## Run Mode

For recorded audio enhancement, use the transactional NIM mode:

```text
STREAMING=false
```

The ComfyUI node default also uses `streaming=false`.

For low-latency experiments, both the container and the ComfyUI node must be
configured for streaming:

```text
STREAMING=true
model_type=48k-ll
```

Use NVIDIA's current Studio Voice NIM quick-start command for the exact image
name and environment variables, then expose gRPC port `8001`.

PowerShell template:

```powershell
$env:NGC_API_KEY = "<your-ngc-api-key>"
$env:NGC_API_KEY | docker login nvcr.io --username '$oauthtoken' --password-stdin

docker run -it --rm --name studio-voice-nim `
  --runtime=nvidia `
  --gpus all `
  --shm-size=8GB `
  -e NGC_API_KEY=$env:NGC_API_KEY `
  -e FILE_SIZE_LIMIT=36700160 `
  -e STREAMING=false `
  -p 8000:8000 `
  -p 8001:8001 `
  nvcr.io/nim/nvidia/studio-voice:latest
```

For `docker login`, paste the NGC key into stdin when prompted, or use a secure
password manager flow. Avoid hardcoding the key in scripts that will be shared.

## GPU Support Caveat

The inspected machine reports an NVIDIA GeForce RTX 5060 Ti with 16 GB VRAM.
NVIDIA's Studio Voice support matrix says RTX-based Blackwell/Ada/Ampere/Turing
GPUs are supported, but the explicit consumer Blackwell rows currently list RTX
5090 and RTX 5080. If the container logs show `NIMProfileIDNotFound`, the node is
fine but the hosted Studio Voice NIM profile did not match the GPU.
