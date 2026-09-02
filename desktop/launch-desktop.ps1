param(
  [string]$Python = "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe",
  [string]$SourceRoot = "D:\personal-life-os"
)

$env:PERSONAL_LIFE_OS_PYTHON = $Python
$env:PERSONAL_LIFE_OS_SOURCE_ROOT = $SourceRoot
$env:PYTHONPATH = Join-Path $SourceRoot "src"

Push-Location (Join-Path $SourceRoot "desktop\src-tauri")
try {
  cargo tauri dev
} finally {
  Pop-Location
}
