[CmdletBinding()]
param(
    [string]$ComposeFile = "",
    [string]$UpdateComposeFile = (Join-Path $PSScriptRoot "compose.auto-update.yaml"),
    [string]$ProjectDirectory = $PSScriptRoot,
    [string]$Image = "ghcr.io/littleweirdlab0514-web/nasdrop:latest",
    [int]$TimeoutSeconds = 180,
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "nasdrop-update-backups")
)

$ErrorActionPreference = "Stop"
if (-not $ComposeFile) {
    $releaseCompose = Join-Path $PSScriptRoot "compose.release.yaml"
    $ComposeFile = if (Test-Path -LiteralPath $releaseCompose -PathType Leaf) {
        $releaseCompose
    } else {
        Join-Path $PSScriptRoot "compose.yaml"
    }
}
if ($TimeoutSeconds -le 0) { throw "TimeoutSeconds must be greater than zero." }
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) { throw "Missing $ComposeFile" }
if (-not (Test-Path -LiteralPath $UpdateComposeFile -PathType Leaf)) { throw "Missing $UpdateComposeFile" }

$lockPath = Join-Path $ProjectDirectory ".nasdrop-update.lock"
try {
    $lock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
} catch {
    throw "Another NASDrop update is already running."
}

function Invoke-Compose {
    param([string]$SelectedImage, [string]$PullPolicy, [string[]]$Arguments)
    $previousImage = $env:NASDROP_UPDATE_IMAGE
    $previousPolicy = $env:NASDROP_UPDATE_PULL_POLICY
    try {
        $env:NASDROP_UPDATE_IMAGE = $SelectedImage
        $env:NASDROP_UPDATE_PULL_POLICY = $PullPolicy
        & docker compose --project-directory $ProjectDirectory -f $ComposeFile -f $UpdateComposeFile @Arguments
        if ($LASTEXITCODE -ne 0) { throw "docker compose failed with exit code $LASTEXITCODE" }
    } finally {
        $env:NASDROP_UPDATE_IMAGE = $previousImage
        $env:NASDROP_UPDATE_PULL_POLICY = $previousPolicy
    }
}

function Get-ServiceContainerId {
    param([string]$SelectedImage, [string]$PullPolicy)
    $previousImage = $env:NASDROP_UPDATE_IMAGE
    $previousPolicy = $env:NASDROP_UPDATE_PULL_POLICY
    try {
        $env:NASDROP_UPDATE_IMAGE = $SelectedImage
        $env:NASDROP_UPDATE_PULL_POLICY = $PullPolicy
        $id = & docker compose --project-directory $ProjectDirectory -f $ComposeFile -f $UpdateComposeFile ps -q nasdrop
        if ($LASTEXITCODE -ne 0) { throw "Unable to locate the nasdrop service." }
        return ($id | Select-Object -First 1).Trim()
    } finally {
        $env:NASDROP_UPDATE_IMAGE = $previousImage
        $env:NASDROP_UPDATE_PULL_POLICY = $previousPolicy
    }
}

function Wait-NASDropHealthy {
    param([string]$SelectedImage, [string]$PullPolicy)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $id = Get-ServiceContainerId $SelectedImage $PullPolicy
        if ($id) {
            $state = & docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $id 2>$null
            if ($LASTEXITCODE -eq 0 -and $state -eq "healthy") { return $true }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

try {
    $containerId = Get-ServiceContainerId $Image "always"
    if (-not $containerId) { throw "The Compose-managed nasdrop service is not running." }

    $oldImageId = (& docker inspect --format '{{.Image}}' $containerId).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Unable to inspect the running NASDrop image." }
    $configSource = (& docker inspect --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}' $containerId).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $configSource) { throw "The /config bind mount was not found." }

    Write-Output "NASDrop update: checking $Image"
    Invoke-Compose $Image "always" @("pull", "nasdrop")
    $newImageId = (& docker image inspect --format '{{.Id}}' $Image).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Unable to inspect the downloaded image." }
    if ($oldImageId -eq $newImageId) {
        Write-Output "NASDrop update: already current."
        return
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $rollbackImage = "nasdrop-local-rollback:$stamp"
    & docker image tag $oldImageId $rollbackImage
    if ($LASTEXITCODE -ne 0) { throw "Unable to retain the rollback image." }

    Write-Output "NASDrop update: stopping NASDrop for a consistent configuration backup."
    Invoke-Compose $Image "always" @("stop", "--timeout", "60", "nasdrop")
    New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
    $backupFile = Join-Path $BackupDirectory "config-$stamp.tar.gz"
    & tar -czf $backupFile -C $configSource .
    if ($LASTEXITCODE -ne 0) {
        Invoke-Compose $Image "always" @("start", "nasdrop")
        throw "Configuration backup failed; the existing container was restarted."
    }

    try {
        Write-Output "NASDrop update: installing the new image."
        Invoke-Compose $Image "always" @("up", "-d", "--no-deps", "nasdrop")
        if (-not (Wait-NASDropHealthy $Image "always")) { throw "The new container did not become healthy." }
        Write-Output "NASDrop update: complete; backup saved to $backupFile"
        Write-Output "NASDrop update: rollback image retained as $rollbackImage"
    } catch {
        Write-Warning "NASDrop update failed; restoring $rollbackImage"
        Invoke-Compose $rollbackImage "never" @("up", "-d", "--no-deps", "nasdrop")
        if (-not (Wait-NASDropHealthy $rollbackImage "never")) {
            throw "Automatic rollback also failed; inspect docker compose logs nasdrop. Original error: $($_.Exception.Message)"
        }
        throw "The previous image was restored. Configuration backup: $backupFile. Original error: $($_.Exception.Message)"
    }
} finally {
    if ($lock) { $lock.Dispose() }
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
