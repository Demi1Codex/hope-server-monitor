"""
shock_config.py — Conexión a GeoBar via API REST

Ejecuta comandos haciendo requests a https://geobar.onrender.com/

Comandos soportados:
  status      → GET /bars — muestra resumen de votos
  reset       → POST /reset-votes — limpia votos
  user-reset  → POST /user-reset — resetea usuarios
  bars        → GET /bars — lista bares con IDs
  connect:URL → cambia la URL (ej: connect:https://otra-url.com)
"""

import requests

BASE_URL = "https://geobar.onrender.com"


def run(host: str, command: str) -> tuple[bool, str]:
    cmd = command.strip()
    base = BASE_URL

    if cmd.startswith("connect:"):
        base = cmd.split(":", 1)[1].strip()
        return True, f"Conectado a {base}"

    try:
        if cmd == "status":
            r = requests.get(f"{base}/bars", timeout=10)
            if not r.ok:
                return False, f"Error {r.status_code}"
            bars = r.json()
            total = {"prendido": 0, "vengan": 0, "paja": 0}
            lines = []
            lines.append(f"{'Bar':<25} {'Prendido':>8} {'Vengan':>8} {'Paja':>8} {'Total':>6}")
            lines.append("-" * 60)
            for b in bars:
                v = b.get("votes", {})
                prendido = v.get("prendido", 0)
                vengan = v.get("vengan", 0)
                paja = v.get("paja", 0)
                total["prendido"] += prendido
                total["vengan"] += vengan
                total["paja"] += paja
                bar_total = prendido + vengan + paja
                lines.append(f"{b['name']:<25} {prendido:>8} {vengan:>8} {paja:>8} {bar_total:>6}")
            lines.append("-" * 60)
            gt = total["prendido"] + total["vengan"] + total["paja"]
            lines.append(f"{'TOTALES':<25} {total['prendido']:>8} {total['vengan']:>8} {total['paja']:>8} {gt:>6}")
            return True, "\n".join(lines)

        elif cmd == "reset":
            r = requests.post(f"{base}/reset-votes", timeout=10)
            if r.ok:
                return True, "Votos limpiados correctamente."
            return False, f"Error {r.status_code}: {r.text}"

        elif cmd in ("user-reset", "userreset"):
            r = requests.post(f"{base}/user-reset", timeout=10)
            if r.ok:
                return True, "Reset de usuarios ejecutado."
            return False, f"Error {r.status_code}: {r.text}"

        elif cmd == "bars":
            r = requests.get(f"{base}/bars", timeout=10)
            if not r.ok:
                return False, f"Error {r.status_code}"
            bars = r.json()
            lines = []
            for b in bars:
                v = b.get("votes", {})
                t = v.get("prendido", 0) + v.get("vengan", 0) + v.get("paja", 0)
                icon = "🔥" if t > 0 else "⚪"
                lines.append(f"{icon} {b['name']:<25} ID:{b['id']:<3}  {b['lat']:.4f},{b['lon']:.4f}")
            return True, "\n".join(lines)

        else:
            return False, f"Comando desconocido: {cmd}. Usa: status, reset, user-reset, bars, connect:IP:PORT"

    except requests.exceptions.ConnectionError:
        return False, f"No se pudo conectar a {base}"
    except Exception as e:
        return False, f"Error: {e}"
