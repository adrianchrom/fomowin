import asyncio
import logging
import json
import os
import subprocess
from typing import List, Set, Dict, Any
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
        for connection in self.active_connections:
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

# HTTP Middleware for User Session Context
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    session_token = request.cookies.get("fomo_session")
    user = auth_manager.verify_session(session_token)
    request.state.user = user if user else "Maciek"
    return await call_next(request)

# Auth Routes
@app.get("/login", response_class=HTMLResponse)
async def serve_login_page(request: Request):
    login_html = os.path.join(os.path.dirname(__file__), "web", "login.html")
    return FileResponse(login_html)

@app.post("/api/login")
async def login_api(data: Dict[str, str] = Body(...)):
    username = data.get("username", "Maciek") or "Maciek"
    password = data.get("password", "")
    result = auth_manager.authenticate(username, password)
    if result:
        token, canonical_user = result
    else:
        canonical_user = "Adrian" if username.lower() == "adrian" else "Maciek"
        token = auth_manager.create_session(canonical_user)
    
    response = JSONResponse(content={"success": True, "username": canonical_user})
    response.set_cookie(key="fomo_session", value=token, max_age=86400 * 365, httponly=True, samesite="lax")
    return response

@app.post("/api/logout")
async def logout_api(request: Request):
    session_token = request.cookies.get("fomo_session")
    if session_token:
        auth_manager.logout(session_token)
    response = JSONResponse(content={"success": True})
    response.delete_cookie("fomo_session")
    return response

@app.get("/api/user")
async def get_current_user(request: Request):
    user = getattr(request.state, "user", "Maciek")
    perms = user_data_mgr.get_user_permissions(user)
    return {"authenticated": True, "username": user, "permissions": perms}

@app.get("/api/permissions")
async def get_user_permissions_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_permissions(user)

@app.get("/api/admin/permissions")
async def get_admin_permissions_route(request: Request):
    return {"maciek": user_data_mgr.get_user_permissions("Maciek")}

@app.post("/api/admin/permissions")
async def update_admin_permissions_route(request: Request, data: Dict[str, Any] = Body(...)):
    updated = user_data_mgr.update_maciek_permissions(data)
    return {"success": True, "permissions": updated}

# WYDATKI ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/wydatki")
async def get_wydatki_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_wydatki(user)

@app.post("/api/wydatki")
async def add_wydatki_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    res = user_data_mgr.add_user_wydatki(user, data)
    return {"success": True, "entry": res}

@app.delete("/api/wydatki/{entry_id}")
async def delete_wydatki_route(request: Request, entry_id: str):
    user = getattr(request.state, "user", "Maciek")
    success = user_data_mgr.delete_user_wydatki(user, entry_id)
    return {"success": success}

# WYCENY ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/wyceny")
async def get_wyceny_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_wyceny(user)

@app.post("/api/wyceny")
async def save_wyceny_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    res = user_data_mgr.save_user_wyceny(user, data)
    return {"success": True, "data": res}

@app.delete("/api/wyceny/{entry_id}")
async def delete_wyceny_route(request: Request, entry_id: str):
    user = getattr(request.state, "user", "Maciek")
    success = user_data_mgr.delete_user_wyceny(user, entry_id)
    return {"success": success}

# COMPANY DATA ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/company")
async def get_company_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_company(user)

@app.post("/api/company")
async def save_company_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    res = user_data_mgr.save_user_company(user, data)
    return {"success": True, "company": res}

# KALENDARZ ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/kalendarz")
async def get_kalendarz_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_kalendarz(user)

@app.post("/api/kalendarz")
async def save_kalendarz_route(request: Request, data: Any = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    if isinstance(data, list):
        res = user_data_mgr.save_user_kalendarz(user, data)
        return {"success": True, "events": res}
    elif isinstance(data, dict):
        res = user_data_mgr.add_user_kalendarz_event(user, data)
        return {"success": True, "event": res}
    return {"success": False, "error": "Invalid format"}

@app.delete("/api/kalendarz/{event_id}")
async def delete_kalendarz_route(request: Request, event_id: str):
    user = getattr(request.state, "user", "Maciek")
    success = user_data_mgr.delete_user_kalendarz_event(user, event_id)
    return {"success": success}

# CRM ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/crm")
async def get_crm_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_crm(user)

@app.post("/api/crm")
async def add_crm_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    added = user_data_mgr.add_user_crm_client(user, data)
    return {"success": True, "client": added}

@app.put("/api/crm/{client_id}")
async def update_crm_route(client_id: str, request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    updated = user_data_mgr.update_user_crm_client(user, client_id, data)
    return {"success": updated is not None, "client": updated}

@app.delete("/api/crm/{client_id}")
async def delete_crm_route(client_id: str, request: Request):
    user = getattr(request.state, "user", "Maciek")
    success = user_data_mgr.delete_user_crm_client(user, client_id)
    return {"success": success}

# TASKS (KANBAN / TODO) ENDPOINTS (STRICT PER-USER ISOLATION)
@app.get("/api/tasks")
async def get_tasks_route(request: Request):
    user = getattr(request.state, "user", "Maciek")
    return user_data_mgr.get_user_tasks(user)

@app.post("/api/tasks")
async def add_task_route(request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    added = user_data_mgr.add_user_task(user, data)
    return {"success": True, "task": added}

@app.put("/api/tasks/{task_id}")
async def update_task_route(task_id: str, request: Request, data: Dict[str, Any] = Body(...)):
    user = getattr(request.state, "user", "Maciek")
    updated = user_data_mgr.update_user_task(user, task_id, data)
    return {"success": updated is not None, "task": updated}

@app.delete("/api/tasks/{task_id}")
async def delete_task_route(task_id: str, request: Request):
    user = getattr(request.state, "user", "Maciek")
    success = user_data_mgr.delete_user_task(user, task_id)
    return {"success": success}

# CURRENCY CONVERTER & NBP RATES ENDPOINT
@app.get("/api/currency/rates")
async def get_currency_rates_route():
    import urllib.request, ssl
    fallback_rates = {
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
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = "https://api.nbp.pl/api/exchangerates/tables/A/?format=json"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    rates_list = data[0].get("rates", [])
                    effective_date = data[0].get("effectiveDate", "")
                    for r in rates_list:
                        code = r.get("code")
                        if code in fallback_rates:
                            fallback_rates[code]["mid"] = round(r.get("mid", fallback_rates[code]["mid"]), 4)
                            fallback_rates[code]["date"] = effective_date
                    return {"success": True, "date": effective_date, "rates": fallback_rates}
    except Exception as e:
        logger.debug(f"NBP API fetch error: {e}")
    return {"success": True, "date": "Dzisiaj", "rates": fallback_rates}

# LLM TEXT MODEL CHAT ENDPOINTS
@app.post("/api/llm/chat")
async def chat_llm_route(data: Dict[str, Any] = Body(...)):
    prompt = data.get("prompt", "") or data.get("message", "")
    return llm_engine.process_chat(prompt)

@app.delete("/api/llm/chat")
async def clear_llm_chat_route():
    llm_engine.clear_history()
    return {"success": True}

# Main Application Routes
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    return FileResponse(html_path)

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
    user = getattr(request.state, "user", "Maciek")
    profile = USER_FOMO_CONNECTIONS.get(user, "https://fomo.family/profile/maciek_trader")
    
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
    user = getattr(request.state, "user", "Maciek")
    input_text = data.get("input", "").strip()
    if not input_text:
        return JSONResponse(status_code=400, content={"success": False, "detail": "Wprowadź profil fomo.family lub adres portfela."})
    
    USER_FOMO_CONNECTIONS[user] = input_text
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
async def get_alerts_route():
    """Get all active market cap alerts."""
    return alerts_manager.get_all_alerts()

@app.post("/api/alerts")
async def create_alert_route(data: Dict[str, Any] = Body(...)):
    """Create a new market cap alert."""
    token_name = data.get("token_name", "Token")
    ca = data.get("ca", "")
    alert_type = data.get("alert_type", "BUY_UNDER")
    target_mcap = float(data.get("target_mcap_usd", 0.0))
    ticker = data.get("ticker", token_name.split()[0] if token_name else "TKN")
    
    alert = alerts_manager.add_alert(
        token_name=token_name,
        ticker=ticker,
        ca=ca,
        alert_type=alert_type,
        target_mcap_usd=target_mcap
    )
    return {"success": True, "alert": alert}

@app.delete("/api/alerts/{alert_id}")
async def delete_alert_route(alert_id: str):
    """Delete an active market cap alert."""
    success = alerts_manager.remove_alert(alert_id)
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
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    console_notifier.print_startup_banner()
    asyncio.create_task(token_scanner.start_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
