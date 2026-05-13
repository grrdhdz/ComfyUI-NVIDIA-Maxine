$ErrorActionPreference = "Stop"

Write-Host "Checking Docker Desktop..."
docker info | Out-Host

Write-Host "Checking NVIDIA GPU visibility from Windows..."
nvidia-smi | Out-Host

Write-Host "Checking GPU access inside Docker..."
docker run --rm --gpus=all nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -gpu -benchmark

