"""Lanceur de Snake Eyes : démarre le serveur si besoin puis ouvre l'application.

Avec Docker installé : démarre Docker Desktop si nécessaire puis le conteneur.
Sinon : lance uvicorn depuis le venv du projet, en arrière-plan.
L'interface s'ouvre ensuite dans une fenêtre d'application Chrome/Edge (sans barre
d'adresse), ou à défaut dans le navigateur par défaut.

Le .pyw s'exécute avec pythonw : aucune fenêtre de console.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8000"
NO_WINDOW = subprocess.CREATE_NO_WINDOW
PROGRAM_DIRS = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
BROWSERS = [
    r"Google\Chrome\Application\chrome.exe",
    r"Microsoft\Edge\Application\msedge.exe",
    r"BraveSoftware\Brave-Browser\Application\brave.exe",
]


def server_up() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=1):
            return True
    except OSError:
        return False


def wait_for(check, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(1)
    return False


def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)


def docker_ready() -> bool:
    return run("docker", "info").returncode == 0


def start_with_docker(status) -> None:
    if not docker_ready():
        status("Démarrage de Docker Desktop…")
        exe = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe"
        if exe.exists():
            subprocess.Popen([str(exe)], creationflags=NO_WINDOW)
        if not wait_for(docker_ready, 180):
            raise RuntimeError("Docker ne répond pas. Lance Docker Desktop puis réessaie.")
    status("Démarrage du conteneur…")
    result = run("docker", "compose", "up", "-d", "--build")
    if result.returncode != 0:
        raise RuntimeError(f"docker compose a échoué :\n\n{result.stderr.strip()[-1500:]}")


def start_with_venv(status) -> None:
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        raise RuntimeError("Ni Docker ni le venv (.venv) ne sont disponibles : voir le README.")
    status("Démarrage du serveur…")
    subprocess.Popen(
        [str(pythonw), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
        creationflags=NO_WINDOW | subprocess.DETACHED_PROCESS,
    )


def open_app() -> None:
    for base in filter(None, PROGRAM_DIRS):
        for rel in BROWSERS:
            exe = Path(base) / rel
            if exe.exists():
                subprocess.Popen([str(exe), f"--app={URL}"])
                return
    webbrowser.open(URL)


def start_server(status) -> None:
    if shutil.which("docker") and (ROOT / "docker-compose.yml").exists():
        start_with_docker(status)
    else:
        start_with_venv(status)
    status("Connexion à Snake Eyes…")
    if not wait_for(server_up, 90):
        raise RuntimeError(f"Le serveur ne répond pas sur {URL}.")


def main() -> None:
    if server_up():
        open_app()
        return

    # Petite fenêtre d'attente pendant le démarrage (Docker peut prendre une minute).
    root = tk.Tk()
    root.title("Snake Eyes")
    root.overrideredirect(True)
    root.configure(bg="#1d1f24")
    icon = ROOT / "launcher" / "snake-eyes.ico"
    if icon.exists():
        root.iconbitmap(str(icon))
    label = tk.Label(root, text="Démarrage…", fg="#e6e6e6", bg="#1d1f24", font=("Segoe UI", 11), padx=32, pady=20)
    label.pack()
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 2
    root.geometry(f"+{x}+{y}")
    root.attributes("-topmost", True)

    outcome: list = []

    def status(text: str) -> None:
        root.after(0, label.config, {"text": text})

    def work() -> None:
        try:
            start_server(status)
            outcome.append(None)
        except Exception as e:  # noqa: BLE001 — tout échec est montré à l'utilisateur
            outcome.append(e)
        root.after(0, root.quit)

    threading.Thread(target=work, daemon=True).start()
    root.mainloop()
    root.withdraw()

    error = outcome[0] if outcome else RuntimeError("Démarrage interrompu.")
    if error is None:
        open_app()
    else:
        messagebox.showerror("Snake Eyes", str(error))
        sys.exit(1)


if __name__ == "__main__":
    main()
