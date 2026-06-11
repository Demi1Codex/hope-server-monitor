"""
auto_betterdiscord.py — Reinstala BetterDiscord automáticamente
cuando Discord PTB se actualiza.

Modos de uso:
    python auto_betterdiscord.py              Monitoreo continuo (watchdog)
    python auto_betterdiscord.py --poll        Monitoreo por polling
    python auto_betterdiscord.py --once        Revisar y reparar una vez
    python auto_betterdiscord.py --install     Forzar instalación ahora
    python auto_betterdiscord.py --startup     Crear autostart en Windows
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CHANNEL = "ptb"
FOLDER_NAME = "DiscordPTB"
PROCESS_NAME = "DiscordPTB.exe"
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
DISCORD_DIR = os.path.join(LOCALAPPDATA, FOLDER_NAME) if LOCALAPPDATA else None
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "state.json"
LOG_FILE = SCRIPT_DIR / "auto_betterdiscord.log"
APP_DIR_PATTERN = re.compile(r"^app-(\d+\.\d+\.\d+)")

log = logging.getLogger("bd-auto")


# ─── Logging ───────────────────────────────────────────────

def setup_logging():
    log.handlers.clear()
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)

    if sys.executable.endswith("python.exe"):
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        log.addHandler(ch)


# ─── State ─────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_version": None, "known_versions": [], "last_install": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── Discord version detection ─────────────────────────────

def get_discord_versions() -> list:
    if not DISCORD_DIR or not os.path.isdir(DISCORD_DIR):
        return []
    versions = []
    for entry in os.listdir(DISCORD_DIR):
        full = os.path.join(DISCORD_DIR, entry)
        m = APP_DIR_PATTERN.match(entry)
        if os.path.isdir(full) and m:
            versions.append((m.group(1), full))
    versions.sort(key=lambda x: list(map(int, x[0].split("."))), reverse=True)
    return versions


def get_latest_version() -> tuple:
    versions = get_discord_versions()
    return versions[0] if versions else (None, None)


# ─── bdcli management ─────────────────────────────────────

def find_bdcli() -> str | None:
    bdcli = shutil.which("bdcli")
    if bdcli:
        return bdcli
    winget_path = Path(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages",
        "betterdiscord.cli_Microsoft.Winget.Source_8wekyb3d8bbwe",
        "bdcli.exe",
    )
    if winget_path.exists():
        return str(winget_path)
    return None


def install_bdcli() -> bool:
    log.info("Instalando bdcli via winget...")
    try:
        r = subprocess.run(
            ["winget", "install", "betterdiscord.cli",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
        if r.returncode == 0:
            log.info("bdcli instalado correctamente")
            return True
        log.error("Error instalando bdcli:\n%s", r.stderr)
        return False
    except Exception as e:
        log.error("Excepción instalando bdcli: %s", e)
        return False


# ─── BetterDiscord operations ─────────────────────────────

def kill_discord():
    log.info("Cerrando Discord...")
    subprocess.run(["taskkill", "/F", "/IM", PROCESS_NAME],
                   capture_output=True, timeout=10)
    time.sleep(3)


def install_bd(bdcli: str) -> bool:
    log.info("Instalando BetterDiscord...")
    kill_discord()
    try:
        r = subprocess.run(
            [bdcli, "install", "--channel", CHANNEL],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
        if r.returncode == 0:
            log.info("BetterDiscord instalado correctamente")
            return True
        log.error("Error instalando BD:\n%s\n%s", r.stdout, r.stderr)
        return False
    except Exception as e:
        log.error("Excepción instalando BD: %s", e)
        return False


def is_bd_installed(bdcli: str) -> bool:
    try:
        r = subprocess.run(
            [bdcli, "status", "--channel", CHANNEL],
            capture_output=True, text=True, errors="replace", timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


# ─── Core check logic ─────────────────────────────────────

def check_and_install(bdcli: str, state: dict) -> bool:
    version, _ = get_latest_version()
    if not version:
        log.warning("No se detectó ninguna versión de Discord")
        return False

    last = state.get("last_version")
    if last == version:
        return False

    log.info("Discord %s → %s", last or "N/A", version)
    ok = install_bd(bdcli)
    if ok:
        state["last_version"] = version
        state["last_install"] = datetime.now().isoformat()
        save_state(state)
    return ok


# ─── Startup ───────────────────────────────────────────────

def setup_startup():
    startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    script = Path(__file__).resolve()
    vbs = startup / "AutoBetterDiscord.vbs"
    vbs.write_text(
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run """{pythonw}"" ""{script}"" --once", 0, False\n',
        encoding="utf-8",
    )
    log.info("Autostart creado: %s", vbs)


# ─── Monitoring modes ─────────────────────────────────────

def run_poll(bdcli: str, state: dict, interval: int = 3600):
    log.info("Modo polling cada %ds", interval)
    while True:
        try:
            check_and_install(bdcli, load_state())
        except Exception as e:
            log.error("Error en polling: %s", e)
        time.sleep(interval)


def run_watchdog(bdcli: str, state: dict):
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    return
                if APP_DIR_PATTERN.match(os.path.basename(event.src_path)):
                    time.sleep(5)
                    log.info("Nuevo directorio detectado: %s", os.path.basename(event.src_path))
                    try:
                        check_and_install(bdcli, load_state())
                    except Exception as e:
                        log.error("Error en watchdog: %s", e)

            def on_moved(self, event):
                dest = event.dest_path
                if os.path.isdir(dest) and APP_DIR_PATTERN.match(os.path.basename(dest)):
                    time.sleep(5)
                    log.info("Directorio renombrado detectado: %s", os.path.basename(dest))
                    try:
                        check_and_install(bdcli, load_state())
                    except Exception as e:
                        log.error("Error en watchdog: %s", e)

        observer = Observer()
        observer.schedule(Handler(), DISCORD_DIR, recursive=False)
        observer.start()
        log.info("Watchdog activo — monitoreando %s", DISCORD_DIR)
        log.info("Presiona Ctrl+C para detener")
        try:
                while True:
                    time.sleep(3600)
                    check_and_install(bdcli, load_state())
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    except ImportError:
        log.warning("watchdog no instalado — cambiando a modo polling")
        run_poll(bdcli, state)


# ─── Main ──────────────────────────────────────────────────

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Auto BetterDiscord Installer")
    parser.add_argument("--once", action="store_true", help="Revisar y reparar una vez")
    parser.add_argument("--install", action="store_true", help="Forzar instalación ahora")
    parser.add_argument("--startup", action="store_true", help="Agregar al inicio de Windows")
    parser.add_argument("--poll", action="store_true", help="Usar polling en vez de watchdog")
    args = parser.parse_args()

    # ── Autostart ──
    if args.startup:
        setup_startup()
        return

    # ── Validar Discord ──
    if not DISCORD_DIR or not os.path.isdir(DISCORD_DIR):
        log.error("Discord PTB no encontrado en %s", DISCORD_DIR)
        log.error("Verifica que Discord PTB esté instalado")
        return

    # ── bdcli ──
    bdcli = find_bdcli()
    if not bdcli:
        log.info("bdcli no encontrado — instalando...")
        if not install_bdcli():
            log.error("No se pudo instalar bdcli. Instálalo manualmente con:")
            log.error("  winget install betterdiscord.cli")
            return
        bdcli = find_bdcli()
        if not bdcli:
            log.error("bdcli no encontrado tras instalación")
            return
    log.info("bdcli: %s", bdcli)

    # ── Verificar / instalar ──
    state = load_state()
    log.info("Versión actual: %s", get_latest_version()[0] or "desconocida")
    check_and_install(bdcli, state)

    if args.install or args.once:
        return

    # ── Monitoreo ──
    if args.poll:
        run_poll(bdcli, state)
    else:
        run_watchdog(bdcli, state)


if __name__ == "__main__":
    main()
