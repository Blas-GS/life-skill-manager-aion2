<#
Keeps a local copy of the app when the project folder is synced by OneDrive.

Called by iniciar.bat. If the project lives inside OneDrive, the code is copied to
%LOCALAPPDATA%\LifeSkillManagerAion2 and the app runs from there, so the Python
environment (.venv), the local database, the offline queue and the temporary
screenshots/videos stay on this computer instead of being uploaded to the cloud.
You keep developing in the OneDrive folder; each launch refreshes the local copy.

Exit codes: 0 = local copy updated, run it; 1 = copy failed; 2 = not a synced folder, run here.
#>
param([Parameter(Mandatory = $true)][string]$Origen)

$origen = (Resolve-Path -LiteralPath $Origen).Path.TrimEnd('\')
$sincronizadas = @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial) | Where-Object { $_ }
$enOneDrive = $sincronizadas | Where-Object { $origen.StartsWith($_.TrimEnd('\') + '\', 'OrdinalIgnoreCase') }
if (-not $enOneDrive) { exit 2 }

$destino = Join-Path $env:LOCALAPPDATA 'LifeSkillManagerAion2'

# Code folders are mirrored: edit in OneDrive, never in the local copy.
foreach ($carpeta in 'app', 'tools', 'supabase') {
    robocopy (Join-Path $origen $carpeta) (Join-Path $destino $carpeta) /MIR /XD __pycache__ /R:1 /W:1 /NJH /NJS /NFL /NDL /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { exit 1 }
}

# Top-level files (.env holds your Supabase settings; missing files are skipped).
robocopy $origen $destino iniciar.bat requirements.txt .env.example .env LICENSE /R:1 /W:1 /NJH /NJS /NFL /NDL /NP | Out-Null
if ($LASTEXITCODE -ge 8) { exit 1 }

# First run only: reuse the recipe catalog instead of downloading it again.
$catalogo = Join-Path $origen 'data\catalogo.json'
$catalogoLocal = Join-Path $destino 'data\catalogo.json'
if ((Test-Path -LiteralPath $catalogo) -and -not (Test-Path -LiteralPath $catalogoLocal)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $catalogoLocal) | Out-Null
    Copy-Item -LiteralPath $catalogo -Destination $catalogoLocal
}
exit 0
