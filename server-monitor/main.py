import asyncio
import importlib.util
import json
import os
import platform
import secrets
import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from supabase import create_client

# ─── Config ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

CHECK_INTERVAL = 30
VALID_TYPES = ("server", "web", "api")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ─── JWT Auth ────────────────────────────────────────
async def get_current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "No autorizado")
    token = auth.split(" ", 1)[1]
    try:
        user = supabase.auth.get_user(token)
        return user.user
    except Exception as e:
        raise HTTPException(401, f"Token inválido: {e}")


# ─── Helpers ─────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


async def ping_host(host: str) -> bool:
    param = "-n" if platform.system().lower() == "windows" else "-c"
    cmd = ["ping", param, "1", host]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        return rc == 0
    except Exception:
        return False


async def check_http(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            return r.status_code < 500
    except Exception:
        return False


async def check_server(server: dict) -> str:
    typ = server.get("type", "server")
    target = server["target"]
    if typ == "server":
        alive = await ping_host(target)
    else:
        alive = await check_http(target)
    return "active" if alive else "inactive"


def _check_role(server_id: str, user_id: str, require_write: bool = False):
    """Check user access to a server. Returns (server_dict, role)."""
    # Owner?
    r = supabase.table("servers").select("*").eq("id", server_id).eq("owner_id", user_id).execute()
    if r.data:
        return r.data[0], "owner"

    # Collaborator?
    c = supabase.table("collaborators").select("role, servers(*)").eq("server_id", server_id).eq("user_id", user_id).execute()
    if c.data:
        role = c.data[0]["role"]
        if require_write and role == "viewer":
            raise HTTPException(403, "No tienes permisos de escritura")
        return c.data[0]["servers"], role

    raise HTTPException(404, "Servidor no encontrado")


# ─── Models ──────────────────────────────────────────
class ServerCreate(BaseModel):
    name: str
    target: str
    type: str = "server"


class ChangeCreate(BaseModel):
    title: str
    description: str = ""
    severity: str = "medium"


class ShockCommand(BaseModel):
    command: str


class ShockConfigBody(BaseModel):
    code: str


# ─── App ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(monitor_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Hope Server Monitor", lifespan=lifespan)


async def monitor_loop():
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            r = supabase.table("servers").select("*").execute()
            servers = r.data
            for srv in servers:
                new_status = await check_server(srv)
                if srv["status"] != new_status:
                    supabase.table("servers").update({
                        "status": new_status,
                        "last_checked": now_iso(),
                    }).eq("id", srv["id"]).execute()
        except Exception:
            pass


# ─── Server endpoints ───────────────────────────────
@app.get("/api/servers")
async def get_servers(user=Depends(get_current_user)):
    uid = user.id

    # Owned
    owned = supabase.table("servers").select("*").eq("owner_id", uid).execute()

    # Collaborated
    collab = supabase.table("collaborators").select("role, server_id, servers(*)").eq("user_id", uid).execute()

    result = []
    for s in owned.data:
        s["_role"] = "owner"
        s["_collab"] = False
        result.append(s)

    for c in collab.data:
        sv = c.get("servers")
        if sv:
            sv["_role"] = c["role"]
            sv["_collab"] = True
            result.append(sv)

    return result


@app.post("/api/servers")
async def add_server(body: ServerCreate, user=Depends(get_current_user)):
    if body.type not in VALID_TYPES:
        raise HTTPException(400, f"Tipo inválido. Válidos: {', '.join(VALID_TYPES)}")

    # Check duplicate target for this user
    dup = supabase.table("servers").select("id").eq("target", body.target).eq("owner_id", user.id).execute()
    if dup.data:
        raise HTTPException(400, "Ya tienes un servidor con ese target")

    server = {
        "id": new_id(),
        "owner_id": user.id,
        "name": body.name,
        "target": body.target,
        "type": body.type,
        "status": "unknown",
        "last_checked": None,
        "created_at": now_iso(),
        "shock_config": "",
    }
    supabase.table("servers").insert(server).execute()
    return server


@app.delete("/api/servers/{server_id}")
async def delete_server(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    if role != "owner":
        raise HTTPException(403, "Solo el propietario puede eliminar")
    supabase.table("servers").delete().eq("id", server_id).execute()
    return {"deleted": True}


@app.post("/api/servers/{server_id}/check")
async def check_single(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    new_status = await check_server(srv)
    supabase.table("servers").update({
        "status": new_status,
        "last_checked": now_iso(),
    }).eq("id", server_id).execute()
    srv["status"] = new_status
    srv["last_checked"] = now_iso()
    return srv


@app.post("/api/check-all")
async def check_all(user=Depends(get_current_user)):
    uid = user.id
    owned = supabase.table("servers").select("*").eq("owner_id", uid).execute()
    for srv in owned.data:
        new_status = await check_server(srv)
        if srv["status"] != new_status:
            supabase.table("servers").update({
                "status": new_status,
                "last_checked": now_iso(),
            }).eq("id", srv["id"]).execute()
    return {"checked": len(owned.data)}


# ─── Change endpoints ───────────────────────────────
@app.get("/api/servers/{server_id}/changes")
async def get_changes(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    r = supabase.table("server_changes").select("*").eq("server_id", server_id).order("timestamp", desc=True).execute()
    return r.data


@app.post("/api/servers/{server_id}/changes")
async def add_change(server_id: str, body: ChangeCreate, user=Depends(get_current_user)):
    if body.severity not in ("low", "medium", "high", "critical"):
        raise HTTPException(400, "Severidad inválida")
    srv, role = _check_role(server_id, user.id, require_write=True)
    change = {
        "id": new_id(),
        "server_id": server_id,
        "title": body.title,
        "description": body.description,
        "severity": body.severity,
        "timestamp": now_iso(),
    }
    supabase.table("server_changes").insert(change).execute()
    return change


# ─── Shock ──────────────────────────────────────────
SHOCK_CONFIG_PATH = BASE_DIR / "shock_config.py"


def _load_shock_runner():
    if not SHOCK_CONFIG_PATH.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("shock_config_plugin", str(SHOCK_CONFIG_PATH))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "run") and callable(mod.run):
            return mod.run
    except Exception:
        pass
    return None


def _compile_runner_from_code(code: str):
    ns = {}
    try:
        exec(compile(code, "<shock_config>", "exec"), ns)
        if callable(ns.get("run")):
            return ns["run"]
    except Exception:
        pass
    return None


@app.post("/api/servers/{server_id}/shock")
async def shock_server(server_id: str, body: ShockCommand, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id, require_write=True)

    target = srv["target"]
    parsed = urlparse(target)
    host = parsed.hostname or (parsed.path.split("/")[0] if "/" in parsed.path else parsed.path) or target
    host = host.split(":")[0]

    runner = None
    server_code = srv.get("shock_config", "")
    if server_code:
        runner = _compile_runner_from_code(server_code)
    if not runner:
        runner = _load_shock_runner()

    if runner:
        try:
            success, output = runner(host, body.command)
            if not isinstance(output, str):
                output = str(output)
        except Exception as e:
            output = f"Error en shock_config.run(): {e}"
            success = False
    else:
        full_cmd = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o UserKnownHostsFile=/dev/null root@{host} '{body.command.replace(chr(39), chr(39)+'\\\"'+chr(39)+'\\\"'+chr(39))}'"
        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
            output = (out + err).decode("utf-8", errors="replace").strip()
            success = proc.returncode == 0
        except Exception as e:
            output = str(e)
            success = False

    change = {
        "id": new_id(),
        "server_id": server_id,
        "title": "Shock ejecutado" if success else "Shock falló",
        "description": f"Host: {host}\nComando: {body.command}\n\nSalida:\n{output}" if output else f"Host: {host}\nComando: {body.command}",
        "severity": "critical",
        "timestamp": now_iso(),
    }
    supabase.table("server_changes").insert(change).execute()

    return {"success": success, "output": output, "host": host}


# ─── Shock Config ───────────────────────────────────
@app.get("/api/servers/{server_id}/shock-config")
async def get_shock_config(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    return {"code": srv.get("shock_config", ""), "active": bool(srv.get("shock_config", ""))}


@app.put("/api/servers/{server_id}/shock-config")
async def save_shock_config(server_id: str, body: ShockConfigBody, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id, require_write=True)
    supabase.table("servers").update({"shock_config": body.code}).eq("id", server_id).execute()
    return {"saved": True}


@app.delete("/api/servers/{server_id}/shock-config")
async def delete_shock_config(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id, require_write=True)
    supabase.table("servers").update({"shock_config": ""}).eq("id", server_id).execute()
    return {"deleted": True}


@app.get("/api/shock-config-status")
async def shock_config_status():
    runner = _load_shock_runner()
    return {"custom": runner is not None}


# ─── Colaboración ──────────────────────────────────
@app.post("/api/servers/{server_id}/invitations")
async def create_invitation(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    if role != "owner":
        raise HTTPException(403, "Solo el propietario puede invitar")

    token = secrets.token_urlsafe(32)
    inv = {
        "id": new_id(),
        "server_id": server_id,
        "token": token,
        "created_by": user.id,
        "used": False,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    supabase.table("invitations").insert(inv).execute()
    return {"token": token, "expires_at": inv["expires_at"]}


@app.get("/api/invitations/{token}")
async def get_invitation(token: str, user=Depends(get_current_user)):
    r = supabase.table("invitations").select("*, servers(name, target)").eq("token", token).execute()
    if not r.data:
        raise HTTPException(404, "Invitación no encontrada")
    inv = r.data[0]
    if inv["used"]:
        raise HTTPException(400, "Invitación ya utilizada")
    expires = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
    if expires < datetime.now(timezone.utc):
        raise HTTPException(400, "Invitación expirada")
    return {
        "server_name": inv["servers"]["name"],
        "server_target": inv["servers"]["target"],
        "expires_at": inv["expires_at"],
    }


@app.post("/api/invitations/{token}/accept")
async def accept_invitation(token: str, user=Depends(get_current_user)):
    r = supabase.table("invitations").select("*").eq("token", token).execute()
    if not r.data:
        raise HTTPException(404, "Invitación no encontrada")
    inv = r.data[0]
    if inv["used"]:
        raise HTTPException(400, "Invitación ya utilizada")
    expires = datetime.fromisoformat(inv["expires_at"].replace("Z", "+00:00"))
    if expires < datetime.now(timezone.utc):
        raise HTTPException(400, "Invitación expirada")

    # Already a collaborator?
    existing = supabase.table("collaborators").select("*").eq("server_id", inv["server_id"]).eq("user_id", user.id).execute()
    if existing.data:
        raise HTTPException(400, "Ya eres colaborador de este servidor")

    collab = {
        "server_id": inv["server_id"],
        "user_id": user.id,
        "role": "viewer",
        "invited_by": inv["created_by"],
    }
    supabase.table("collaborators").insert(collab).execute()
    supabase.table("invitations").update({"used": True}).eq("id", inv["id"]).execute()
    return {"ok": True, "server_id": inv["server_id"]}


@app.get("/api/servers/{server_id}/collaborators")
async def list_collaborators(server_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    if role not in ("owner", "admin"):
        raise HTTPException(403, "No tienes permisos")
    r = supabase.table("collaborators").select("*").eq("server_id", server_id).execute()
    return r.data


@app.delete("/api/collaborators/{server_id}/{collab_user_id}")
async def remove_collaborator(server_id: str, collab_user_id: str, user=Depends(get_current_user)):
    srv, role = _check_role(server_id, user.id)
    if role != "owner":
        raise HTTPException(403, "Solo el propietario puede eliminar colaboradores")
    supabase.table("collaborators").delete().eq("server_id", server_id).eq("user_id", collab_user_id).execute()
    return {"deleted": True}


# ─── Me ─────────────────────────────────────────────
@app.get("/api/me")
async def get_me(user=Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


# ─── Static files ──────────────────────────────────
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.exception_handler(404)
async def spa_fallback(req, exc):
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        return FileResponse(str(STATIC_DIR / "index.html"))
    raise exc


if __name__ == "__main__":
    import uvicorn
    print("  *  Hope Server Monitor — Multi-usuario")
    print("  =>  http://localhost:8000")
    print()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
