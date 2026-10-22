# Gera build\dist\Baixou (programa) e build\installer\Baixou-Setup.exe (instalador).
# Antes: ponha ffmpeg.exe, ffprobe.exe (+ DLLs) e node.exe em build\bin\
$R = $PSScriptRoot
Set-Location $R

# O PyInstaller escreve o progresso no stderr; no PowerShell 5.1 isso não é erro.
# Por isso conferimos o código de saída em vez de usar ErrorActionPreference=Stop.
$ErrorActionPreference = "Continue"
python -m PyInstaller --noconfirm --clean --windowed --name Baixou --icon "$R\assets\baixou.ico" `
  --add-data "$R\app;app" --add-data "$R\site;site" --add-data "$R\assets;assets" `
  --collect-data yt_dlp_ejs --collect-submodules yt_dlp `
  --distpath build\dist --workpath build\work --specpath build server.py 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (código $LASTEXITCODE)" }
$ErrorActionPreference = "Stop"

# Ferramentas e licenças ficam ao lado do .exe (fora do PyInstaller, para não duplicar DLLs).
Copy-Item build\bin build\dist\Baixou\bin -Recurse -Force
Copy-Item build\licenses build\dist\Baixou\licenses -Recurse -Force

& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /Q installer\baixou.iss
Write-Host "Pronto: build\installer\Baixou-Setup.exe"
