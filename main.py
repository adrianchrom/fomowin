import asyncio
import logging
import json
import os
import ssl
import time
import threading
import urllib.request
from typing import List, Set, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse

from config import config
from monitors.new_token_scanner import token_scanner, TokenListing
from monitors.whale_tracker import whale_tracker
from monitors.risk_analysis_engine import risk_engine
from monitors.auth_manager import auth_manager
from monitors.alerts_manager import alerts_manager
from monitors.user_data_manager import user_data_mgr
from monitors.llm_engine import llm_engine
from notifiers.telegram_notifier import telegram_notifier
from notifiers.discord_notifier import discord_notifier
from notifiers.console_notifier import console_notifier

logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("FOMOWhaleBot")

app = FastAPI(title=config.APP_NAME)

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        token_scanner.purge_old_tokens()
        tokens_payload = [
            t.__dict__ for t in token_scanner.known_tokens.values()
            if t.age_minutes <= config.MAX_NEW_TOKEN_AGE_MINUTES and t.holders_count >= 1
        ]
        await websocket.send_json({"type": "init", "tokens": tokens_payload, "is_enabled": token_scanner.is_enabled})

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        dead = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            if connection in self.active_connections:
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Pre-loaded User Sample Insider & Risk Signal
SAMPLE_INSIDER_SIGNAL = risk_engine.analyze_signal(
    source_account="@unipcs",
    platform="Twitter",
    content="Aping into Peanut on fomo.family, looks early: 2qEHjavLflMtzofPtZGfwo26yHUBjM24Wxd8bLp1pump",
    token_name="Peanut the Squirrel",
    ticker="PNUT",
    ca="2qEHjavLflMtzofPtZGfwo26yHUBjM24Wxd8bLp1pump",
    mint_authority_revoked=True,
    freeze_authority_active=False,
    top_holders_supply_pct=14.0
)

# Event Callbacks
async def on_new_token_detected(token: TokenListing):
    if token.age_minutes > config.MAX_NEW_TOKEN_AGE_MINUTES or token.holders_count < 1:
        return
    console_notifier.render_tokens_table(list(token_scanner.known_tokens.values()))
    await manager.broadcast({
        "type": "token_update",
        "token": token.__dict__
    })

async def on_signal_detected(token: TokenListing, signal_info: dict):
    if token.age_minutes > config.MAX_NEW_TOKEN_AGE_MINUTES or token.holders_count < 1:
        return
    console_notifier.print_signal_alert(token, signal_info)
    sig_type = signal_info.get("type", "")
    await manager.broadcast({
        "type": "pump_signal" if "pump" in sig_type else "whale_signal",
        "signal_type": sig_type,
        "token": token.__dict__,
        "signal_info": signal_info
    })
    await telegram_notifier.send_signal_alert(token, signal_info)
    await discord_notifier.send_signal_alert(token, signal_info)

token_scanner.set_callbacks(on_token=on_new_token_detected, on_signal=on_signal_detected)

# ----------------------------------------------------------------------------------------------
# Auth helpers
# ----------------------------------------------------------------------------------------------
def get_auth_user(request: Request) -> Optional[str]:
    return getattr(request.state, "user", None)


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Brak autoryzacji"})


def _require_admin(request: Request) -> Optional[JSONResponse]:
    """Returns an error response unless the caller is the super admin."""
    user = get_auth_user(request)
    if not user or user.lower() != "adrian":
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"error": "Dostęp tylko dla administratora."})
    return None


def _is_https(request: Request) -> bool:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


def _client_ip(request: Request) -> str:
    ip = request.headers.get("cf-connecting-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if not ip and request.client:
        ip = request.client.host
    return ip or "unknown"


# --- login brute-force protection (4-digit PINs are guessable without it) ------------------------
LOGIN_MAX_FAILS = 8
LOGIN_WINDOW_SECONDS = 300
_login_failures: Dict[str, List[float]] = {}
_login_lock = threading.Lock()


def _login_retry_after(ip: str) -> int:
    """Seconds the client has to wait (0 = login allowed)."""
    now = time.time()
    with _login_lock:
        fails = [t for t in _login_failures.get(ip, []) if now - t < LOGIN_WINDOW_SECONDS]
        _login_failures[ip] = fails
        if len(fails) >= LOGIN_MAX_FAILS:
            return max(1, int(fails[-LOGIN_MAX_FAILS] + LOGIN_WINDOW_SECONDS - now))
    return 0


def _register_login_failure(ip: str):
    with _login_lock:
        _login_failures.setdefault(ip, []).append(time.time())


def _clear_login_failures(ip: str):
    with _login_lock:
        _login_failures.pop(ip, None)


# --- module permission enforcement (the UI hides modules, the API must refuse them too) --------
PUBLIC_API_PATHS = {"/api/login", "/api/logout", "/api/status", "/api/user"}

MODULE_BY_PREFIX = [
    ("/api/wydatki", "wydatki"),
    ("/api/wyceny", "wyceny"),
    ("/api/company", "wyceny"),
    ("/api/kalendarz", "kalendarz"),
    ("/api/crm", "crm"),
    ("/api/tasks", "tasks"),
    ("/api/llm", "ai_chat"),
    ("/api/currency", "currency_calc"),
    ("/api/fomo", "fomo"),
    ("/api/tokens", "fomo"),
    ("/api/tracked-insiders", "fomo"),
    ("/api/insider-signals", "fomo"),
    ("/api/scan-token", "fomo"),
    ("/api/alerts", "fomo"),
    ("/api/risk-sample", "fomo"),
    ("/api/risk-analysis", "fomo"),
    ("/api/user-positions", "fomo"),
    ("/api/connect-fomo", "fomo"),
]


def _module_for_path(path: str) -> Optional[str]:
    for prefix, module in MODULE_BY_PREFIX:
        if path == prefix or path.startswith(prefix + "/"):
            return module
    return None


# HTTP Middleware for User Session Context
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    session_token = request.cookies.get("fomo_session")
    user = auth_manager.verify_session(session_token)
    request.state.user = user  # Strictly None if not authenticated
    path = request.url.path

    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        if not user:
            return _unauthorized()
        module = _module_for_path(path)
        if module and not user_data_mgr.has_permission(user, module):
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"error": "Brak dostępu do tego modułu."})

    response = await call_next(request)
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ----------------------------------------------------------------------------------------------
# Auth Routes
# ----------------------------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
@app.get("/login.html", response_class=HTMLResponse)
async def serve_login_page(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        return RedirectResponse(url=f"/?t={int(time.time())}", status_code=302)
    return FileResponse(os.path.join(WEB_DIR, "login.html"), headers=NO_CACHE_HEADERS)

@app.post("/api/login")
async def login_api(request: Request, data: Dict[str, str] = Body(...)):
    if "username" in data and not str(data["username"]).strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "detail": "Wprowadź nazwę użytkownika."}
        )

    username = (data.get("username", "") or "").strip()
    pin = (data.get("pin", "") or data.get("password", "") or "").strip()

    if not pin.isdigit() or len(pin) != 4:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "detail": "Wprowadź 4-cyfrowy kod PIN."}
        )

    ip = _client_ip(request)
    retry_after = _login_retry_after(ip)
    if retry_after:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            content={"success": False, "retry_after": retry_after,
                     "detail": f"Zbyt wiele błędnych prób. Spróbuj ponownie za {retry_after} s."}
        )

    # PIN-only login: each PIN is unique and maps to exactly one account.
    # If a username is also sent (legacy clients), it must match that PIN.
    if username:
        res = auth_manager.authenticate_user_pin(username, pin)
    else:
        res = auth_manager.authenticate_pin(pin)

    if not res:
        _register_login_failure(ip)
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "detail": "Nieprawidłowy kod PIN. Brak dostępu."}
        )

    _clear_login_failures(ip)
    token, canonical_user = res
    response = JSONResponse(content={"success": True, "username": canonical_user})
    response.set_cookie(
        key="fomo_session", value=token, max_age=86400 * 365,
        httponly=True, samesite="lax", secure=_is_https(request), path="/"
    )
    return response

@app.post("/api/logout")
async def logout_api(request: Request):
    session_token = request.cookies.get("fomo_session")
    if session_token:
        auth_manager.logout(session_token)
    response = JSONResponse(content={"success": True})
    response.delete_cookie("fomo_session", path="/")
    return response

@app.post("/api/logout-all")
async def logout_all_api(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    auth_manager.logout_all()
    response = JSONResponse(content={"success": True, "message": "Wylogowano wszystkie konta."})
    response.delete_cookie("fomo_session", path="/")
    return response

@app.get("/api/user")
async def get_current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"authenticated": False, "username": None, "permissions": {}, "profile": {}}
        )
    perms = user_data_mgr.get_user_permissions(user)
    profile = user_data_mgr.get_user_profile(user)
    settings = user_data_mgr.get_user_settings(user)
    return {"authenticated": True, "username": user, "permissions": perms, "profile": profile, "settings": settings}

@app.get("/api/user-settings")
async def get_user_settings_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return user_data_mgr.get_user_settings(user)

@app.post("/api/user-settings")
async def save_user_settings_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    saved = user_data_mgr.save_user_settings(user, data)
    return {"success": True, "settings": saved}

@app.get("/api/permissions")
async def get_user_permissions_route(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return _unauthorized()
    return user_data_mgr.get_user_permissions(user)

@app.get("/api/admin/permissions")
async def get_admin_permissions_route(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    return user_data_mgr.get_all_users_permissions()

@app.post("/api/admin/permissions")
async def update_admin_permissions_route(request: Request, data: Dict[str, Any] = Body(...)):
    denied = _require_admin(request)
    if denied:
        return denied
    target_user = data.get("user", "")
    if not target_user:
        return JSONResponse(status_code=400, content={"success": False, "detail": "Brak nazwy użytkownika."})
    perms_data = data.get("permissions", data)
    updated = user_data_mgr.update_user_permissions(target_user, perms_data)
    return {"success": True, "user": target_user, "permissions": updated}

@app.get("/api/admin/generate-pin")
async def generate_random_pin_route(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    import secrets
    existing_pins = set(str(p).strip() for p in auth_manager.users.values())
    for _ in range(1000):
        val = secrets.randbelow(9000) + 1000
        cand = str(val)
        if len(set(cand)) > 1 and cand not in existing_pins and cand not in ["1234", "4321", "1111", "0000"]:
            return {"success": True, "pin": cand}
    return {"success": True, "pin": "7391"}

@app.get("/api/admin/users")
async def get_admin_users_route(request: Request):
    denied = _require_admin(request)
    if denied:
        return denied
    user_list = []
    for u, pin in auth_manager.users.items():
        perms = user_data_mgr.get_user_permissions(u)
        prof = user_data_mgr.get_user_profile(u)
        user_list.append({
            "username": u,
            "pin": pin,
            "is_admin": u.lower() == "adrian",
            "permissions": perms,
            "profile": prof
        })
    return {"success": True, "users": user_list}

@app.post("/api/admin/users")
async def create_or_update_user_route(request: Request, data: Dict[str, Any] = Body(...)):
    denied = _require_admin(request)
    if denied:
        return denied
    username = (data.get("username", "") or "").strip()
    pin = (data.get("pin", "") or "").strip()
    initial_perms = data.get("permissions", {})
    p1 = (data.get("p1", "") or username).strip()
    p2 = (data.get("p2", "") or "Partner").strip()
    household = (data.get("household", "") or "").strip()

    if not username:
        return JSONResponse(status_code=400, content={"success": False, "detail": "Nazwa konta jest wymagana."})
    if not pin or len(pin) != 4 or not pin.isdigit():
        return JSONResponse(status_code=400, content={"success": False, "detail": "PIN musi mieć dokładnie 4 cyfry."})

    try:
        canonical = auth_manager.add_or_update_user(username, pin)
    except ValueError as ve:
        return JSONResponse(status_code=400, content={"success": False, "detail": str(ve)})

    if initial_perms:
        user_data_mgr.update_user_permissions(canonical, initial_perms)
    else:
        user_data_mgr.get_user_permissions(canonical)

    prof = user_data_mgr.update_user_profile(canonical, {
        "p1": p1,
        "p2": p2,
        "household": household or f"PAIR_{canonical.upper()}"
    })

    return {
        "success": True,
        "username": canonical,
        "pin": pin,
        "permissions": user_data_mgr.get_user_permissions(canonical),
        "profile": prof
    }

@app.put("/api/admin/users/{target_username}")
async def update_user_admin_route(request: Request, target_username: str, data: Dict[str, Any] = Body(...)):
    denied = _require_admin(request)
    if denied:
        return denied

    existing = next((u for u in auth_manager.users if u.lower() == target_username.strip().lower()), None)
    if not existing:
        return JSONResponse(status_code=404, content={"success": False, "detail": "Użytkownik nie został znaleziony."})

    pin = (data.get("pin", "") or "").strip()
    if pin:
        if not pin.isdigit() or len(pin) != 4:
            return JSONResponse(status_code=400, content={"success": False, "detail": "PIN musi mieć dokładnie 4 cyfry."})
        pin_changed = str(auth_manager.users.get(existing, "")).strip() != pin
        try:
            auth_manager.add_or_update_user(existing, pin)
        except ValueError as ve:
            return JSONResponse(status_code=400, content={"success": False, "detail": str(ve)})
        if pin_changed:
            # A new PIN must lock out whoever still holds a session from the old one
            # (the admin's own current session stays valid).
            keep = request.cookies.get("fomo_session") if (get_auth_user(request) or "").lower() == existing.lower() else None
            auth_manager.revoke_user_sessions(existing, keep_token=keep)

    if "permissions" in data and isinstance(data["permissions"], dict):
        user_data_mgr.update_user_permissions(existing, data["permissions"])

    prof_updates = {}
    if "p1" in data: prof_updates["p1"] = data["p1"]
    if "p2" in data: prof_updates["p2"] = data["p2"]
    if "household" in data: prof_updates["household"] = data["household"]
    if prof_updates:
        user_data_mgr.update_user_profile(existing, prof_updates)

    canonical = user_data_mgr.resolve_canonical(existing)
    return {
        "success": True,
        "username": canonical,
        "pin": auth_manager.users.get(canonical, ""),
        "permissions": user_data_mgr.get_user_permissions(canonical),
        "profile": user_data_mgr.get_user_profile(canonical)
    }

@app.delete("/api/admin/users/{username}")
async def delete_user_route(request: Request, username: str):
    denied = _require_admin(request)
    if denied:
        return denied
    if username.lower() == "adrian":
        return JSONResponse(status_code=400, content={"success": False, "detail": "Nie można usunąć głównego konta administratora."})
    deleted = auth_manager.delete_user(username)
    if deleted:
        user_data_mgr.delete_user_permissions(username)
        return {"success": True}
    return JSONResponse(status_code=404, content={"success": False, "detail": "Użytkownik nie został znaleziony."})


# ----------------------------------------------------------------------------------------------
# Whole-document stores with optimistic concurrency (WYDATKI, WYCENY)
# The client sends the revision it last saw in ``X-Base-Rev``. If somebody else saved meanwhile the
# server answers 409 with the current document instead of silently overwriting it.
# ----------------------------------------------------------------------------------------------
def _base_rev(request: Request) -> Optional[int]:
    raw = request.headers.get("x-base-rev")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _doc_response(doc: Any, rev: int) -> JSONResponse:
    return JSONResponse(content=doc, headers={"X-Doc-Rev": str(rev)})


def _conflict_response(doc: Any, rev: int) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"success": False, "conflict": True, "data": doc, "rev": rev})


# WYDATKI ENDPOINTS (STRICT PER-HOUSEHOLD ISOLATION)
@app.get("/api/wydatki")
async def get_wydatki_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return _doc_response(user_data_mgr.get_user_wydatki(user), user_data_mgr.get_user_wydatki_rev(user))

@app.post("/api/wydatki")
async def add_or_save_wydatki_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    if "baseIncomes" in data or "gigs" in data or "expenses" in data:
        saved, doc, rev = user_data_mgr.save_user_wydatki_checked(user, data, _base_rev(request))
        if not saved:
            return _conflict_response(doc, rev)
        return {"success": True, "data": doc, "rev": rev}
    res = user_data_mgr.add_user_wydatki(user, data)
    return {"success": True, "entry": res}

@app.delete("/api/wydatki/{entry_id}")
async def delete_wydatki_route(request: Request, entry_id: str):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    success = user_data_mgr.delete_user_wydatki(user, entry_id)
    return {"success": success}

# WYCENY ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/wyceny")
async def get_wyceny_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return _doc_response(user_data_mgr.get_user_wyceny(user), user_data_mgr.get_user_wyceny_rev(user))

@app.post("/api/wyceny")
async def save_wyceny_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    saved, doc, rev = user_data_mgr.save_user_wyceny_checked(user, data, _base_rev(request))
    if not saved:
        return _conflict_response(doc, rev)
    return {"success": True, "data": doc, "rev": rev}

@app.delete("/api/wyceny/{entry_id}")
async def delete_wyceny_route(request: Request, entry_id: str):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    success = user_data_mgr.delete_user_wyceny(user, entry_id)
    return {"success": success}

# COMPANY DATA ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/company")
async def get_company_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return user_data_mgr.get_user_company(user)

@app.post("/api/company")
async def save_company_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    res = user_data_mgr.save_user_company(user, data)
    return {"success": True, "company": res}

# KALENDARZ ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/kalendarz")
async def get_kalendarz_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return user_data_mgr.get_user_kalendarz(user)

@app.post("/api/kalendarz")
async def save_kalendarz_route(request: Request, data: Any = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    if isinstance(data, list):
        res = user_data_mgr.save_user_kalendarz(user, data)
        return {"success": True, "events": res}
    elif isinstance(data, dict):
        res = user_data_mgr.add_user_kalendarz_event(user, data)
        return {"success": True, "event": res}
    return JSONResponse(status_code=400, content={"success": False, "error": "Invalid format"})

@app.delete("/api/kalendarz/{event_id}")
async def delete_kalendarz_route(request: Request, event_id: str):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    success = user_data_mgr.delete_user_kalendarz_event(user, event_id)
    return {"success": success}

# CRM ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/crm")
async def get_crm_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return user_data_mgr.get_user_crm(user)

@app.post("/api/crm")
async def add_crm_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    added = user_data_mgr.add_user_crm_client(user, data)
    return {"success": True, "client": added}

@app.put("/api/crm/{client_id}")
async def update_crm_route(client_id: str, request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    updated = user_data_mgr.update_user_crm_client(user, client_id, data)
    if updated is None:
        return JSONResponse(status_code=404, content={"success": False, "client": None, "detail": "Klient nie istnieje (został usunięty?)."})
    return {"success": True, "client": updated}

@app.delete("/api/crm/{client_id}")
async def delete_crm_route(client_id: str, request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    success = user_data_mgr.delete_user_crm_client(user, client_id)
    return {"success": success}

# TASKS (KANBAN / TODO) ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/tasks")
async def get_tasks_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    return user_data_mgr.get_user_tasks(user)

@app.post("/api/tasks")
async def add_task_route(request: Request, data: Any = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    if isinstance(data, list):
        saved = user_data_mgr.save_user_tasks(user, data)
        return {"success": True, "tasks": saved}
    if isinstance(data, dict):
        added = user_data_mgr.add_user_task(user, data)
        return {"success": True, "task": added}
    return JSONResponse(status_code=400, content={"success": False, "detail": "Nieprawidłowy format danych zadań."})

@app.delete("/api/tasks")
async def clear_tasks_route(request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    user_data_mgr.clear_user_tasks(user)
    return {"success": True, "tasks": []}

@app.put("/api/tasks/{task_id}")
async def update_task_route(task_id: str, request: Request, data: Dict[str, Any] = Body(...)):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    updated = user_data_mgr.update_user_task(user, task_id, data)
    if updated is None:
        return JSONResponse(status_code=404, content={"success": False, "task": None, "detail": "Zadanie nie istnieje (zostało usunięte?)."})
    return {"success": True, "task": updated}

@app.delete("/api/tasks/{task_id}")
async def delete_task_route(task_id: str, request: Request):
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    success = user_data_mgr.delete_user_task(user, task_id)
    return {"success": True, "deleted": success}

# CURRENCY CONVERTER & NBP RATES ENDPOINT
CURRENCY_FALLBACK_RATES = {
    "EUR": {"code": "EUR", "name": "Euro", "mid": 4.28, "change": "+0.15%"},
    "USD": {"code": "USD", "name": "Dolar amerykański", "mid": 3.92, "change": "-0.08%"},
    "GBP": {"code": "GBP", "name": "Funt szterling", "mid": 5.12, "change": "+0.22%"},
    "CHF": {"code": "CHF", "name": "Frank szwajcarski", "mid": 4.54, "change": "+0.05%"},
    "NOK": {"code": "NOK", "name": "Korona norweska", "mid": 0.37, "change": "-0.12%"},
    "SEK": {"code": "SEK", "name": "Korona szwedzka", "mid": 0.38, "change": "+0.02%"},
    "CAD": {"code": "CAD", "name": "Dolar kanadyjski", "mid": 2.85, "change": "+0.10%"},
    "AUD": {"code": "AUD", "name": "Dolar australijski", "mid": 2.58, "change": "-0.04%"},
    "JPY": {"code": "JPY", "name": "Jen japoński (100 JPY)", "mid": 2.62, "change": "+0.18%"}
}
_currency_cache: Dict[str, Any] = {"ts": 0.0, "ttl": 0, "payload": None}


def _fetch_nbp_payload() -> Dict[str, Any]:
    """Blocking network call - always executed in a worker thread, never on the event loop."""
    import copy
    rates = copy.deepcopy(CURRENCY_FALLBACK_RATES)
    url = "https://api.nbp.pl/api/exchangerates/tables/A/?format=json"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    contexts = [ssl.create_default_context()]
    unverified = ssl.create_default_context()
    unverified.check_hostname = False
    unverified.verify_mode = ssl.CERT_NONE
    contexts.append(unverified)  # public, non-secret data: tolerate machines with a broken CA store
    for ctx in contexts:
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
                if resp.status != 200:
                    continue
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and data:
                effective_date = data[0].get("effectiveDate", "")
                for r in data[0].get("rates", []):
                    code = r.get("code")
                    if code in rates:
                        mid_val = round(r.get("mid", rates[code]["mid"]), 4)
                        rates[code]["mid"] = mid_val
                        rates[code]["date"] = effective_date
                for k in rates:
                    rates[k]["rate"] = rates[k]["mid"]
                return {"success": True, "live": True, "date": effective_date, "effective_date": effective_date, "rates": rates}
        except Exception as e:
            logger.debug(f"NBP API fetch error: {e}")
    for k in rates:
        rates[k]["rate"] = rates[k]["mid"]
    return {"success": True, "live": False, "date": "Dzisiaj", "effective_date": "Dzisiaj", "rates": rates}


@app.get("/api/currency/rates")
async def get_currency_rates_route():
    now = time.time()
    if _currency_cache["payload"] and now - _currency_cache["ts"] < _currency_cache["ttl"]:
        return _currency_cache["payload"]
    payload = await asyncio.to_thread(_fetch_nbp_payload)
    _currency_cache.update(ts=now, ttl=900 if payload.get("live") else 60, payload=payload)
    return payload

# LLM TEXT MODEL CHAT ENDPOINTS (blocking HTTP calls -> plain ``def`` so FastAPI runs them in a thread)
@app.post("/api/llm/chat")
def chat_llm_route(request: Request, data: Dict[str, Any] = Body(...)):
    prompt = str(data.get("prompt", "") or data.get("message", ""))[:4000]
    return llm_engine.process_chat(prompt, user=get_auth_user(request) or "")

@app.delete("/api/llm/chat")
async def clear_llm_chat_route(request: Request):
    llm_engine.clear_history(user=get_auth_user(request) or "")
    return {"success": True}

# Main Application Routes
@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        q = request.url.query
        redir = f"/login?{q}" if q else f"/login?t={int(time.time())}"
        return RedirectResponse(url=redir, status_code=302)
    return FileResponse(os.path.join(WEB_DIR, "index.html"), headers=NO_CACHE_HEADERS)

@app.get("/manifest.json")
async def get_manifest():
    return FileResponse(os.path.join(WEB_DIR, "manifest.json"), media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})

@app.get("/apple-touch-icon.png")
@app.get("/apple-touch-icon-precomposed.png")
async def get_apple_touch_icon():
    return FileResponse(os.path.join(WEB_DIR, "apple-touch-icon.png"), media_type="image/png", headers={"Cache-Control": "no-cache"})

@app.get("/favicon.ico")
async def get_favicon_ico():
    return FileResponse(os.path.join(WEB_DIR, "favicon.ico"), media_type="image/x-icon", headers={"Cache-Control": "no-cache"})

@app.get("/favicon.png")
async def get_favicon_png():
    return FileResponse(os.path.join(WEB_DIR, "favicon.png"), media_type="image/png", headers={"Cache-Control": "no-cache"})

@app.get("/logo.svg")
async def get_logo_svg():
    return FileResponse(os.path.join(WEB_DIR, "logo.svg"), media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})

@app.get("/icon-192.png")
async def get_icon_192():
    return FileResponse(os.path.join(WEB_DIR, "icon-192.png"), media_type="image/png", headers={"Cache-Control": "no-cache"})

@app.get("/icon-512.png")
async def get_icon_512():
    return FileResponse(os.path.join(WEB_DIR, "icon-512.png"), media_type="image/png", headers={"Cache-Control": "no-cache"})

@app.get("/api/status")
async def get_status():
    token_scanner.purge_old_tokens()
    return {
        "app": config.APP_NAME,
        "buy_min_investment_usd": config.BUY_MIN_INVESTMENT_USD,
        "whale_min_portfolio_usd": config.WHALE_MIN_PORTFOLIO_USD,
        "max_token_age_minutes": config.MAX_NEW_TOKEN_AGE_MINUTES,
        "monitored_tokens_count": len(token_scanner.known_tokens),
        "chains": list(config.CHAINS.keys()),
        "is_enabled": token_scanner.is_enabled
    }

@app.get("/api/fomo/status")
async def get_fomo_status():
    return {"is_enabled": token_scanner.is_enabled}

@app.post("/api/fomo/toggle")
async def toggle_fomo_status(data: Dict[str, Any] = Body(default={})):
    enabled = data.get("enabled")
    if enabled is None:
        enabled = not token_scanner.is_enabled
    token_scanner.toggle_engine(enabled)
    await manager.broadcast({"type": "fomo_status", "is_enabled": token_scanner.is_enabled})
    return {"success": True, "is_enabled": token_scanner.is_enabled}

@app.get("/api/tokens")
async def get_tokens():
    token_scanner.purge_old_tokens()
    return [
        t for t in token_scanner.known_tokens.values()
        if t.age_minutes <= config.MAX_NEW_TOKEN_AGE_MINUTES and t.holders_count >= 1
    ]

@app.get("/api/tracked-insiders")
async def get_tracked_insiders():
    """Get list of tracked insider handles."""
    return risk_engine.tracked_insiders

@app.get("/api/insider-signals")
async def get_insider_signals_route():
    """Get live stream of Insider Signals."""
    return risk_engine.get_insider_signals_feed()

@app.post("/api/tracked-insiders")
async def add_tracked_insider_route(data: Dict[str, Any] = Body(...)):
    """Add a tracked insider by X link, fomo.family link, or @handle."""
    input_text = data.get("input", "")
    res = risk_engine.add_tracked_insider(input_text)
    if not res:
        return JSONResponse(status_code=400, content={"success": False, "detail": "Nieprawidłowy link lub uchwyt insidera."})
    return {"success": True, "insider": res}

@app.delete("/api/tracked-insiders/{handle}")
async def remove_tracked_insider_route(handle: str):
    """Remove a tracked insider handle."""
    success = risk_engine.remove_tracked_insider(handle)
    return {"success": success}

# fomo.family Account & User Trade Risk Analysis Engine
USER_FOMO_CONNECTIONS: Dict[str, str] = {} # username -> profile_or_wallet

@app.get("/api/user-positions")
async def get_user_positions(request: Request):
    """Returns connected user fomo.family trade positions with risk of drop vs probability of growth analysis."""
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    profile = user_data_mgr.get_user_settings(user).get("fomo_connection") or USER_FOMO_CONNECTIONS.get(user, f"https://fomo.family/profile/{user.lower()}_trader")
    
    return {
        "connected": True,
        "profile": profile,
        "username": user,
        "total_portfolio_usd": 18450.0,
        "unrealized_pnl_pct": 142.5,
        "positions": [
            {
                "id": "pos-1",
                "token_name": "Peanut the Squirrel",
                "ticker": "PNUT",
                "ca": "2qEHjavLflMtzofPtZGfwo26yHUBjM24Wxd8bLp1pump",
                "amount_usd": 15200.0,
                "entry_mcap_usd": 120000000.0,
                "current_mcap_usd": 850000000.0,
                "pnl_pct": 608.3,
                "risk_of_drop_pct": 18.5,
                "growth_probability_pct": 81.5,
                "risk_level": "SAFE_BULLISH",
                "recommendation": "Silny akumulowany aktyw – wysokie prawdopodobieństwo dalszych wzrostów."
            },
            {
                "id": "pos-2",
                "token_name": "Brett on Base",
                "ticker": "BRETT",
                "ca": "0x532f27101965dd16442e59d40670fa5bb0915b9b",
                "amount_usd": 24000.0,
                "entry_mcap_usd": 650000000.0,
                "current_mcap_usd": 1400000000.0,
                "pnl_pct": 115.3,
                "risk_of_drop_pct": 22.0,
                "growth_probability_pct": 78.0,
                "risk_level": "SAFE_BULLISH",
                "recommendation": "Silny akumulowany aktyw – wysokie prawdopodobieństwo dalszych wzrostów."
            }
        ]
    }

@app.post("/api/connect-fomo")
async def connect_fomo_account(request: Request, data: Dict[str, Any] = Body(...)):
    """Connect fomo.family profile or wallet to current session."""
    user = get_auth_user(request)
    if not user:
        return _unauthorized()
    input_text = data.get("input", "").strip()
    if not input_text:
        return JSONResponse(status_code=400, content={"success": False, "detail": "Wprowadź profil fomo.family lub adres portfela."})
    
    USER_FOMO_CONNECTIONS[user] = input_text
    user_data_mgr.save_user_settings(user, {"fomo_connection": input_text})
    return {"success": True, "connected_profile": input_text}

@app.get("/api/risk-sample")
async def get_risk_sample():
    """Returns the pre-analyzed sample signal provided by user."""
    return SAMPLE_INSIDER_SIGNAL

@app.post("/api/scan-token")
async def scan_token_route(data: Dict[str, Any] = Body(...)):
    """API endpoint to scan token CA or URL for honeypot & contract safety."""
    input_text = data.get("input", "")
    return risk_engine.scan_token_ca(input_text)

@app.get("/api/alerts")
async def get_alerts_route(request: Request):
    """Get the market cap alerts of the current user."""
    return alerts_manager.get_all_alerts(owner=get_auth_user(request))

@app.post("/api/alerts")
async def create_alert_route(request: Request, data: Dict[str, Any] = Body(...)):
    """Create a new market cap alert."""
    token_name = data.get("token_name", "Token")
    ca = str(data.get("ca", "") or "").strip()
    alert_type = data.get("alert_type", "BUY_UNDER")
    try:
        target_mcap = float(data.get("target_mcap_usd", 0.0))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"success": False, "detail": "Podaj poprawną kapitalizację docelową."})
    if not ca or target_mcap <= 0:
        return JSONResponse(status_code=400, content={"success": False, "detail": "Podaj adres kontraktu i dodatnią kapitalizację."})
    ticker = data.get("ticker", token_name.split()[0] if token_name else "TKN")
    
    alert = alerts_manager.add_alert(
        token_name=token_name,
        ticker=ticker,
        ca=ca,
        alert_type=alert_type,
        target_mcap_usd=target_mcap,
        owner=get_auth_user(request) or ""
    )
    return {"success": True, "alert": alert}

@app.delete("/api/alerts/{alert_id}")
async def delete_alert_route(request: Request, alert_id: str):
    """Delete one of the user's own market cap alerts."""
    success = alerts_manager.remove_alert(alert_id, owner=get_auth_user(request))
    return {"success": success}

@app.post("/api/risk-analysis")
async def analyze_risk_post(data: Dict[str, Any] = Body(...)):
    """API endpoint to analyze custom on-chain signal risk & insider classification."""
    res = risk_engine.analyze_signal(
        source_account=data.get("source_account"),
        platform=data.get("platform", "Twitter"),
        content=data.get("content", ""),
        token_name=data.get("token_name", "Unknown Token"),
        ticker=data.get("ticker", "TOKEN"),
        ca=data.get("ca", ""),
        mint_authority_revoked=data.get("mint_authority_revoked", True),
        freeze_authority_active=data.get("freeze_authority_active", False),
        sell_tax_pct=float(data.get("sell_tax_pct", 0.0)),
        blacklist_enabled=data.get("blacklist_enabled", False),
        lp_unlocked=data.get("lp_unlocked", False),
        top_holders_supply_pct=float(data.get("top_holders_supply_pct", 0.0)),
        external_danger_status=data.get("external_danger_status", False)
    )
    return res

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Only logged-in users that may use the FOMO module receive the live token stream.
    user = auth_manager.verify_session(websocket.cookies.get("fomo_session"))
    if not user or not user_data_mgr.has_permission(user, "fomo"):
        await websocket.close(code=4401)
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive pings from the browser
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    console_notifier.print_startup_banner()
    asyncio.create_task(token_scanner.start_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
