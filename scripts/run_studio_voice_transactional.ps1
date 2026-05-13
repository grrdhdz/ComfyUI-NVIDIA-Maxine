param(
    [Parameter(Mandatory = $false)]
    [string]$NgcApiKey = $env:NGC_API_KEY,

    [Parameter(Mandatory = $false)]
    [string]$ModelProfile = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($NgcApiKey)) {
    throw "Set NGC_API_KEY or pass -NgcApiKey. The key is used only to pull/cache NIM resources."
}

$NgcApiKey | docker login nvcr.io --username '$oauthtoken' --password-stdin

$dockerArgs = @(
    "run", "-it", "--rm",
    "--name", "studio-voice-nim",
    "--runtime=nvidia",
    "--gpus", "all",
    "--shm-size=8GB",
    "-e", "NGC_API_KEY=$NgcApiKey",
    "-e", "FILE_SIZE_LIMIT=36700160",
    "-e", "STREAMING=false",
    "-p", "8000:8000",
    "-p", "8001:8001"
)

if (-not [string]::IsNullOrWhiteSpace($ModelProfile)) {
    $dockerArgs += @("-e", "NIM_MODEL_PROFILE=$ModelProfile")
}

$dockerArgs += "nvcr.io/nim/nvidia/studio-voice:latest"

docker @dockerArgs
