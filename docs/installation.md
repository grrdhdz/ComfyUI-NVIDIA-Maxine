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
