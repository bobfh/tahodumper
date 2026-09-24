# PowerShell installer/downloader for TahoCard Dumper
$ErrorActionPreference = 'Stop'
$url = "https://raw.githubusercontent.com/bobfh/tahodumper/main/release/TahoDumper.exe"
$destDir = $PWD.Path
$outFile = Join-Path $destDir "TahoDumper.exe"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  TahoCard Dumper - Download & Run              " -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Destination: $destDir" -ForegroundColor Gray
Write-Host "Downloading from GitHub: $url ..." -ForegroundColor Yellow

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $outFile -UseBasicParsing

Write-Host "[+] Downloaded successfully: $outFile" -ForegroundColor Green
Write-Host "[*] Starting TahoDumper..." -ForegroundColor Cyan
Start-Process -FilePath $outFile
