"""First-run bootstrapper — stdlib only (runs under the bundled embeddable
Python before any pip package exists).

Flow: check whether requirements are already installed (a marker file keyed by
the requirements hash). If not, ask the user for permission via a native
Windows dialog, then ``pip install`` them into the bundled interpreter with a
visible console, and finally launch the GUI. Subsequent runs skip straight to
launch.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REQ_FILE = os.path.join(APP_DIR, "requirements.txt")
MAIN = os.path.join(APP_DIR, "main.py")

# Reuse the engine's data-dir resolution (stdlib-only module).
sys.path.insert(0, APP_DIR)
from engine import paths  # noqa: E402

MARKER = os.path.join(str(paths.DATA_DIR), ".deps_ok")


def _req_hash() -> str:
    try:
        with open(REQ_FILE, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def _deps_ready() -> bool:
    want = _req_hash()
    if not want:
        return True  # no requirements file → nothing to install
    try:
        with open(MARKER, encoding="utf-8") as f:
            return f.read().strip() == want
    except OSError:
        return False


def _ask_yes_no(title: str, text: str) -> bool:
    """Native Yes/No prompt on Windows; console fallback elsewhere."""
    if os.name == "nt":
        import ctypes
        MB_YESNO, MB_ICONQUESTION = 0x04, 0x20
        ret = ctypes.windll.user32.MessageBoxW(0, text, title, MB_YESNO | MB_ICONQUESTION)
        return ret == 6  # IDYES
    try:
        return input(f"{title}\n{text} [s/N] ").strip().lower() in ("s", "y", "sim", "yes")
    except EOFError:
        return False


def _error_box(title: str, text: str) -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    else:
        print(f"ERROR: {title}: {text}", file=sys.stderr)


def _install() -> bool:
    ok = _ask_yes_no(
        "Rastreador de Preços — Instalação",
        "Na primeira execução é necessário baixar os componentes do programa "
        "(interface e rede, ~100 MB). Isso é feito uma única vez, dentro desta "
        "pasta portátil, sem alterar o sistema.\n\nInstalar agora?",
    )
    if not ok:
        return False
    print("Instalando componentes… isso pode levar alguns minutos.\n")
    cmd = [sys.executable, "-m", "pip", "install", "--no-warn-script-location",
           "--disable-pip-version-check", "-r", REQ_FILE]
    try:
        proc = subprocess.run(cmd)
    except Exception as e:
        _error_box("Falha na instalação", f"Não foi possível executar o pip:\n{e}")
        return False
    if proc.returncode != 0:
        _error_box("Falha na instalação",
                   "A instalação dos componentes falhou. Verifique a conexão com a "
                   "internet e tente novamente.")
        return False
    os.makedirs(str(paths.DATA_DIR), exist_ok=True)
    with open(MARKER, "w", encoding="utf-8") as f:
        f.write(_req_hash())
    print("\nComponentes instalados com sucesso.\n")
    return True


def _launch() -> int:
    return subprocess.run([sys.executable, MAIN]).returncode


def main() -> int:
    if not _deps_ready():
        if not _install():
            return 1
    return _launch()


if __name__ == "__main__":
    sys.exit(main())
