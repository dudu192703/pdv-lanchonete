$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (!(Test-Path ".venv\Scripts\python.exe")) {
    py -m venv .venv
}
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
& $python -m pip install "pyinstaller>=6,<7"
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name "PDV Lanchonete" --add-data "web;web" --hidden-import "uvicorn.logging" --hidden-import "uvicorn.loops.auto" --hidden-import "uvicorn.loops.asyncio" --hidden-import "uvicorn.protocols.http.auto" --hidden-import "uvicorn.protocols.http.h11_impl" --hidden-import "uvicorn.lifespan.on" --hidden-import "uvicorn.lifespan.off" desktop_app.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o executavel" }
$exe = Join-Path $PSScriptRoot "dist\PDV Lanchonete\PDV Lanchonete.exe"
$shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "PDV Lanchonete.lnk"
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
$link.TargetPath = $exe
$link.WorkingDirectory = Split-Path $exe
$link.Description = "PDV Lanchonete offline"
$link.Save()
Write-Host "Pronto! Abra o atalho PDV Lanchonete na Area de Trabalho."
