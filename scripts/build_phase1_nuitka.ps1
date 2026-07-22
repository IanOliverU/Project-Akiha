param(
    [string]$OutputDir = "dist\nuitka"
)

$ErrorActionPreference = "Stop"

python -m nuitka `
    --standalone `
    --assume-yes-for-downloads `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --output-dir=$OutputDir `
    --include-data-dir=assets=assets `
    --include-data-dir=project_akiha/config=project_akiha/config `
    project_akiha/app/main.py

