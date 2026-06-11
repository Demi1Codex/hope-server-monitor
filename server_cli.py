import requests
import json
import os
import sys
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".server_url")


def load_url():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return f.read().strip()
    return ""


def save_url(url):
    with open(CONFIG_FILE, "w") as f:
        f.write(url.strip())


def resolve_url(input_url):
    if not input_url:
        return ""
    input_url = input_url.strip()
    if input_url.startswith("http://") or input_url.startswith("https://"):
        return input_url.rstrip("/")
    return f"http://{input_url}:3000"


def cmd_reset(base_url):
    try:
        r = requests.post(f"{base_url}/reset-votes", timeout=10)
        if r.ok:
            print("  Votos limpiados correctamente.")
        else:
            print(f"  Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"  Error de conexion: {e}")


def cmd_status(base_url):
    try:
        r = requests.get(f"{base_url}/bars", timeout=10)
        if not r.ok:
            print(f"  Error: {r.status_code}")
            return
        bars = r.json()
        total = {"prendido": 0, "vengan": 0, "paja": 0}
        print(f"\n  {'Bar':<25} {'Prendido':>8} {'Vengan':>8} {'Paja':>8} {'Total':>6}")
        print("  " + "-" * 60)
        for b in bars:
            v = b.get("votes", {})
            prendido = v.get("prendido", 0)
            vengan = v.get("vengan", 0)
            paja = v.get("paja", 0)
            bar_total = prendido + vengan + paja
            total["prendido"] += prendido
            total["vengan"] += vengan
            total["paja"] += paja
            print(f"  {b['name']:<25} {prendido:>8} {vengan:>8} {paja:>8} {bar_total:>6}")
        print("  " + "-" * 60)
        gt = total["prendido"] + total["vengan"] + total["paja"]
        print(f"  {'TOTALES':<25} {total['prendido']:>8} {total['vengan']:>8} {total['paja']:>8} {gt:>6}\n")
    except Exception as e:
        print(f"  Error de conexion: {e}")


def cmd_user_reset(base_url):
    try:
        r = requests.post(f"{base_url}/user-reset", timeout=10)
        if r.ok:
            data = r.json()
            print(f"  Reset de usuarios ejecutado. Las apps limpiaran sus votos locales.")
        else:
            print(f"  Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"  Error de conexion: {e}")


def cmd_bars(base_url):
    try:
        r = requests.get(f"{base_url}/bars", timeout=10)
        if not r.ok:
            print(f"  Error: {r.status_code}")
            return
        bars = r.json()
        for b in bars:
            v = b.get("votes", {})
            t = v.get("prendido", 0) + v.get("vengan", 0) + v.get("paja", 0)
            icon = "🔥" if t > 0 else "⚪"
            print(f"  {icon} {b['name']:<25} ID:{b['id']:<3}  {b['lat']:.4f},{b['lon']:.4f}")
    except Exception as e:
        print(f"  Error de conexion: {e}")


def print_help():
    print("""
  Comandos disponibles:
    reset         Limpiar todos los votos
    user-reset    Resetear usuarios (pueden votar de nuevo en bares ya votados)
    status        Mostrar resumen de votos
    bars          Listar todos los bares
    connect       Cambiar la URL del servidor
    help          Mostrar esta ayuda
    exit          Salir del panel
  """)


def main():
    args_url = ""
    if len(sys.argv) > 1 and sys.argv[1] == "--url":
        args_url = sys.argv[2] if len(sys.argv) > 2 else ""

    saved_url = load_url()
    base_url = resolve_url(saved_url)

    if args_url:
        base_url = resolve_url(args_url)
        if base_url:
            save_url(args_url)

    if not base_url:
        print("GeoBar - Panel de Control")
        print("=" * 40)
        user_input = input("URL del servidor (ej: https://geobar.onrender.com o 192.168.1.50): ").strip()
        if user_input:
            base_url = resolve_url(user_input)
            save_url(user_input)

    if not base_url:
        print("No se configuro ninguna URL. Saliendo.")
        sys.exit(1)

    print(f"\n  GeoBar - Panel de Control")
    print(f"  Conectado a: {base_url}")
    print(f"  Escribe 'help' para ver comandos o 'exit' para salir.\n")

    while True:
        try:
            cmd = input("geobar> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if cmd in ("exit", "quit", "q"):
            break
        elif cmd == "reset":
            cmd_reset(base_url)
        elif cmd in ("user-reset", "userreset"):
            cmd_user_reset(base_url)
        elif cmd == "status":
            cmd_status(base_url)
        elif cmd == "bars":
            cmd_bars(base_url)
        elif cmd == "connect":
            new_url = input("  Nueva URL: ").strip()
            if new_url:
                resolved = resolve_url(new_url)
                if resolved:
                    base_url = resolved
                    save_url(new_url)
                    print(f"  Conectado a: {base_url}")
                else:
                    print("  URL invalida.")
        elif cmd == "help":
            print_help()
        elif cmd == "":
            continue
        else:
            print(f"  Comando desconocido: {cmd}. Escribe 'help'.")


if __name__ == "__main__":
    main()
