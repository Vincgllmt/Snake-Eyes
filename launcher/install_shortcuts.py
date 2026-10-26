"""Crée les raccourcis « Snake Eyes » sur le Bureau et dans le menu Démarrer.

Usage (une seule fois) : .venv\\Scripts\\python launcher\\install_shortcuts.py
Les raccourcis lancent launcher/launch.pyw avec le pythonw du venv (sans console).
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
LAUNCHER = ROOT / "launcher" / "launch.pyw"
ICON = ROOT / "launcher" / "snake-eyes.ico"


def ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def main() -> None:
    if not PYTHONW.exists():
        raise SystemExit(f"venv introuvable ({PYTHONW}) : voir « Lancement sans Docker » dans le README.")
    script = f"""
$shell = New-Object -ComObject WScript.Shell
$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($dir in $dirs) {{
    $lnk = $shell.CreateShortcut((Join-Path $dir 'Snake Eyes.lnk'))
    $lnk.TargetPath = {ps_quote(PYTHONW)}
    $lnk.Arguments = '"' + {ps_quote(LAUNCHER)} + '"'
    $lnk.WorkingDirectory = {ps_quote(ROOT)}
    $lnk.IconLocation = {ps_quote(ICON)} + ',0'
    $lnk.Description = 'Snake Eyes : assistant MJ'
    $lnk.Save()
    Write-Output $lnk.FullName
}}
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


if __name__ == "__main__":
    main()
