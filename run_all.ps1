# Launches both Streamlit apps:
#   - Shell  (app.py)        on port 8501  <- open this in your browser
#   - Legacy (app_legacy.py) on port 8502  <- embedded by the shell's
#                                            "Research Setup" page iframe
#
# Run from this folder:
#     .\run_all.ps1
#
# Stop both with Ctrl+C (closes this window; the two child windows must
# also be closed manually, or use: Get-Process streamlit | Stop-Process).

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# Pick the python interpreter — prefer .venv if present.
$venvPy = Join-Path $here '.venv\Scripts\python.exe'
if (Test-Path $venvPy) { $py = $venvPy } else { $py = 'python' }

Write-Host "Starting legacy DNL pipeline app on http://localhost:8502 ..." -ForegroundColor Cyan
Start-Process -FilePath $py `
    -ArgumentList @('-m','streamlit','run','app_legacy.py',
                    '--server.port','8502',
                    '--server.headless','true',
                    '--server.enableCORS','false',
                    '--server.enableXsrfProtection','false',
                    '--browser.gatherUsageStats','false') `
    -WorkingDirectory $here

Start-Sleep -Seconds 2

Write-Host "Starting Competitive Intelligence shell on http://localhost:8501 ..." -ForegroundColor Cyan
& $py -m streamlit run app.py `
    --server.port 8501 `
    --browser.gatherUsageStats false
