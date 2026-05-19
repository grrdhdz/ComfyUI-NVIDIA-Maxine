# Installation

These nodes are designed to be cloned into a local ComfyUI `custom_nodes`
folder. They use ComfyUI's V3 custom node API.

## Requirements

- Windows with Docker Desktop and the WSL2 engine enabled.
- NVIDIA GPU with Docker GPU access working.
- ComfyUI with the V3 custom node API. The package has been developed against
  ComfyUI `0.21.0`.
- Python packages from `requirements.txt`.
- An NGC Personal API key with access to the NVIDIA Studio Voice NIM image.

Studio Voice is the only supported workflow in this package.

## Docker Desktop

Install Docker Desktop for Windows from Docker's official installation guide:

https://docs.docker.com/desktop/setup/install/windows-install/

Use Docker Desktop's WSL2 backend. Docker's GPU support documentation states
that GPU support in Docker Desktop is available on Windows with the WSL2
backend:

https://docs.docker.com/desktop/features/gpu/

Start Docker Desktop before running the ComfyUI setup node. The nodes call
`docker.exe` from Windows; users do not need to open a WSL shell.

## NVIDIA NGC API Key

Studio Voice uses NVIDIA's local NIM Docker image:

```text
nvcr.io/nim/nvidia/studio-voice:latest
```

NVIDIA's Studio Voice NIM getting-started page documents the NGC API key and
Docker login flow:

https://docs.nvidia.com/nim/maxine/studio-voice/latest/getting-started.html

Before the first pull:

1. Sign in to NVIDIA/NGC.
2. Open the Studio Voice deploy page and accept terms if prompted:
   https://build.nvidia.com/nvidia/studiovoice/deploy
3. Create an NGC Personal API key:
   https://org.ngc.nvidia.com/setup/api-keys
4. Include at least the `NGC Catalog` service for the key.

For Docker login, the username is the literal `$oauthtoken`; the password is the
NGC API key. The ComfyUI setup node handles this for normal users.

## Manual Install

From PowerShell:

```powershell
cd C:\path\to\ComfyUI\custom_nodes
git clone https://github.com/grrdhdz/ComfyUI-NVIDIA-Maxine.git
cd ComfyUI-NVIDIA-Maxine
..\..\python_embeded\python.exe -m pip install -r requirements.txt
```

For Comfy Desktop or a virtualenv-based install, use the Python executable that
launches that ComfyUI installation:

```powershell
C:\path\to\ComfyUI\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Restart ComfyUI after installing dependencies.

## ComfyUI Manager

When installed through ComfyUI Manager or cloned manually, the important file is
`requirements.txt`. There is no `requirements.py`; Python dependencies for
ComfyUI custom nodes are normally declared in `requirements.txt`.

If nodes do not appear after cloning:

1. Confirm the repository folder is directly under `custom_nodes`.
2. Install `requirements.txt` with the same Python used by ComfyUI.
3. Restart ComfyUI and check the startup log for import errors.

## Docker/NIM Setup

Docker images are not downloaded during Python package installation. The
ComfyUI setup node performs Docker login, image pull, container start, and
health checks when the user runs it.

For Studio Voice:

1. Add `NVIDIA Studio Voice Docker Setup`.
2. Paste the NGC API key, or leave the field empty and launch ComfyUI with
   `NGC_API_KEY` set in the environment.
3. Run `setup_all_transactional`.
4. Connect `studio_voice_connection` to `NVIDIA Studio Voice Enhance`.

Saved ComfyUI workflows may retain widget values. For shared workflows, do not
save API keys inside nodes.

## Example Workflow

This repository includes an importable ComfyUI workflow:

```text
workflows/nvidia_studio_voice_enhance.json
```

Import it with `Workflow -> Open` or drag it onto the ComfyUI canvas. The API
key field is blank by design.
