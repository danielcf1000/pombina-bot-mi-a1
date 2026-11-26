# Sube la app Surf Galicia al Xiaomi Mi A1 y la deja en /srv/surf-galicia,
# que es la carpeta que publica Tailscale Funnel (ver docs/surf-galicia.md).
# Uso (PowerShell, desde la carpeta del repo):  .\herramientas\subir-surf.ps1
param(
    [string]$Origen   = "$env:USERPROFILE\Documents\surf-galicia-app",
    [string]$Servidor = "a1"   # alias de ~\.ssh\config (WiFi). Por USB: a1-usb
)
$ErrorActionPreference = 'Stop'

function Ejecuta([string]$que, [scriptblock]$cmd) {
    Write-Host "-> $que"
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "Fallo: $que (codigo $LASTEXITCODE)" }
}

$archivos = Get-ChildItem -File -Path $Origen | ForEach-Object { $_.FullName }
if (-not $archivos) { throw "No hay archivos en $Origen" }
if (-not (Test-Path (Join-Path $Origen 'index.html'))) { throw "Falta index.html en $Origen" }

Ejecuta "Preparando carpeta temporal en el movil" { ssh $Servidor "rm -rf /tmp/surf-galicia && mkdir -p /tmp/surf-galicia" }
Ejecuta "Copiando $($archivos.Count) archivos" { scp @archivos "${Servidor}:/tmp/surf-galicia/" }
Ejecuta "Instalando en /srv/surf-galicia" {
    ssh $Servidor "sudo mkdir -p /srv/surf-galicia && sudo find /srv/surf-galicia -mindepth 1 -delete && sudo cp /tmp/surf-galicia/* /srv/surf-galicia/ && sudo chmod -R a+rX /srv/surf-galicia && rm -rf /tmp/surf-galicia && ls -l /srv/surf-galicia"
}
Write-Host "Listo. Si el movil ya tenia la app abierta, la version nueva aparece al abrirla la segunda vez."
