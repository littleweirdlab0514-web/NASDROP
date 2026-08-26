param(
  [string]$NodeVersion = "22.13.1",
  [string]$NodeVariant = "linux-x64-glibc-217",
  [string]$NodeSha256 = "9c0927b3cdccce0d5d5196b9076cfbd356a4ad7214cd147631a74837e52ba88e",
  [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$workRoot = Join-Path $PSScriptRoot ".build"
$cacheRoot = Join-Path $PSScriptRoot ".cache"
$innerRoot = Join-Path $workRoot "inner"
$outerRoot = Join-Path $workRoot "outer"
$distRoot = Join-Path $PSScriptRoot "dist"
$nodeArchiveName = "node-v$NodeVersion-$NodeVariant.tar.xz"
$nodeArchive = Join-Path $cacheRoot $nodeArchiveName
$nodeUrl = "https://unofficial-builds.nodejs.org/download/release/v$NodeVersion/$nodeArchiveName"
$packageVersion = "0.7.14-1"

if ($PythonPath) {
  $pythonExe = $PythonPath
  $pythonArgs = @()
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonExe = (Get-Command python).Source
  $pythonArgs = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonExe = (Get-Command py).Source
  $pythonArgs = @("-3")
} else {
  throw "Python 3 is required to create a DSM-compatible SPK"
}

if (Test-Path -LiteralPath $workRoot) { Remove-Item -LiteralPath $workRoot -Recurse -Force }
New-Item -ItemType Directory -Path $innerRoot,$outerRoot,$distRoot,$cacheRoot -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $repoRoot "backend.py") -Destination $innerRoot
Copy-Item -LiteralPath (Join-Path $repoRoot "gofile_wt.mjs") -Destination $innerRoot
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination $innerRoot
Copy-Item -LiteralPath (Join-Path $repoRoot "THIRD_PARTY_NOTICES.md") -Destination $innerRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "web") -Destination $innerRoot -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "package-inner\ui") -Destination $innerRoot -Recurse
New-Item -ItemType Directory -Path (Join-Path $innerRoot "licenses") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "licenses\nodejs-LICENSE.txt") -Destination (Join-Path $innerRoot "licenses\nodejs-LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "web\qrcode-LICENSE.txt") -Destination (Join-Path $innerRoot "licenses\qrcode-LICENSE.txt")

if (-not (Test-Path -LiteralPath $nodeArchive)) {
  Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeArchive
}
$actualNodeSha256 = (Get-FileHash -LiteralPath $nodeArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualNodeSha256 -ne $NodeSha256.ToLowerInvariant()) {
  throw "Node.js runtime SHA-256 verification failed"
}
$nodeExtract = Join-Path $workRoot "node"
New-Item -ItemType Directory -Path $nodeExtract -Force | Out-Null
& tar.exe -xJf $nodeArchive -C $nodeExtract "node-v$NodeVersion-$NodeVariant/bin/node"
if ($LASTEXITCODE -ne 0) { throw "Node.js runtime extraction failed" }
New-Item -ItemType Directory -Path (Join-Path $innerRoot "bin") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $nodeExtract "node-v$NodeVersion-$NodeVariant\bin\node") -Destination (Join-Path $innerRoot "bin\node")

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "package\INFO") -Destination $outerRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "package\conf") -Destination $outerRoot -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "package\scripts") -Destination $outerRoot -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "PACKAGE_ICON.PNG") -Destination $outerRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "PACKAGE_ICON_256.PNG") -Destination $outerRoot
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination $outerRoot

$spkPath = Join-Path $distRoot "nasdrop-$packageVersion-x86_64.spk"
if (Test-Path -LiteralPath $spkPath) { Remove-Item -LiteralPath $spkPath -Force }
& $pythonExe @pythonArgs (Join-Path $PSScriptRoot "pack_spk.py") --inner $innerRoot --outer $outerRoot --output $spkPath --version $packageVersion
if ($LASTEXITCODE -ne 0) { throw "SPK creation or validation failed" }
Write-Output $spkPath
