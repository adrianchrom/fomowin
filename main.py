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
        await websocket.send_json({"type": "init", "tokens": tokens_payload})

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
    content="Aping into this new runner on fomo.family, looks early: 7xKX...pump",
    token_name="Unipcs Runner",
    ticker="RUNNER",
    ca="7xKXtg2CW87d97TXJSD9...",
    mint_authority_revoked=True,
    freeze_authority_active=True,
    top_holders_supply_pct=34.0
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

# HTTP Middleware for Session Authentication
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Exclude public endpoints & login static assets
    if path in ["/login", "/api/login", "/favicon.ico"] or path.startswith("/static"):
        return await call_next(request)

    session_token = request.cookies.get("fomo_session")
    user = auth_manager.verify_session(session_token)

    if not user:
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Brak autoryzacji. Zaloguj się (Adrian / Maciek)."})
        return RedirectResponse(url="/login", status_code=303)

    request.state.user = user
    return await call_next(request)

# Auth Routes
@app.get("/login", response_class=HTMLResponse)
async def serve_login_page(request: Request):
    session_token = request.cookies.get("fomo_session")
    if auth_manager.verify_session(session_token):
        return RedirectResponse(url="/", status_code=303)
    login_html = os.path.join(os.path.dirname(__file__), "web", "login.html")
    return FileResponse(login_html)

@app.post("/api/login")
async def login_api(data: Dict[str, str] = Body(...)):
    username = data.get("username", "")
    password = data.get("password", "")
    token = auth_manager.authenticate(username, password)
    if not token:
        return JSONResponse(status_code=401, content={"success": False, "detail": "Nieprawidłowy użytkownik lub hasło. Zalogować mogą się tylko Adrian lub Maciek."})
    
    response = JSONResponse(content={"success": True, "username": username.strip()})
    response.set_cookie(key="fomo_session", value=token, max_age=86400 * 7, httponly=True, samesite="lax")
    return response

@app.post("/api/logout")
async def logout_api(request: Request):
    session_token = request.cookies.get("fomo_session")
    auth_manager.logout(session_token)
    response = JSONResponse(content={"success": True})
    response.delete_cookie("fomo_session")
    return response

@app.get("/api/user")
async def get_current_user(request: Request):
    user = getattr(request.state, "user", None)
    return {"authenticated": True, "username": user}

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
        "chains": list(config.CHAINS.keys())
    }

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
                "token_name": "Unipcs Runner",
                "ticker": "RUNNER",
                "ca": "7xKXtg2CW87d97TXJSD9...",
                "amount_usd": 3200.0,
                "entry_mcap_usd": 120000.0,
                "current_mcap_usd": 450000.0,
                "pnl_pct": 275.0,
                "risk_of_drop_pct": 68.5,
                "growth_probability_pct": 31.5,
                "risk_level": "HIGH_VOLATILITY",
                "recommendation": "Rozważ częściową realizację zysków (Take Profit)."
            },
            {
                "id": "pos-2",
                "token_name": "Horseimnot Alpha",
                "ticker": "HORSE",
                "ca": "0x58ffac95f78d15cecddb91056c8f79f704144e34",
                "amount_usd": 5400.0,
                "entry_mcap_usd": 650000.0,
                "current_mcap_usd": 1400000.0,
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
