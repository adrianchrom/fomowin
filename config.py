import os
from dataclasses import dataclass, field
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # General Settings
    APP_NAME: str = "FOMO Whale & 0-30m Pump Signal Bot"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

    # STRICT TOKEN AGE CONSTRAINT: 0 to 30 MINUTES MAXIMUM!
    MAX_NEW_TOKEN_AGE_MINUTES: float = float(os.getenv("MAX_NEW_TOKEN_AGE_MINUTES", "30.0"))

    # Buyer Investment Threshold ($2,500 USD+)
    BUY_MIN_INVESTMENT_USD: float = float(os.getenv("BUY_MIN_INVESTMENT_USD", "2500.0"))

    # Whale Net Worth Threshold ($500,000 USD+)
    WHALE_MIN_PORTFOLIO_USD: float = float(os.getenv("WHALE_MIN_PORTFOLIO_USD", "500000.0"))
    WHALE_MIN_BUY_USD: float = float(os.getenv("WHALE_MIN_BUY_USD", "1000.0"))

    # 5-Minute Pump Criteria
    PUMP_5M_TARGET_PCT: float = float(os.getenv("PUMP_5M_TARGET_PCT", "5000.0"))        # +5,000% (50x)
    MEGA_PUMP_5M_TARGET_PCT: float = float(os.getenv("MEGA_PUMP_5M_TARGET_PCT", "20000.0")) # +20,000% (200x)

    # Scanning intervals (in seconds)
    SCAN_INTERVAL_SECONDS: float = float(os.getenv("SCAN_INTERVAL_SECONDS", "3.0"))

    # Webhook & Bot Alerts
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Network RPC Nodes
    RPC_ROBINHOOD: str = os.getenv("RPC_ROBINHOOD", "https://rpc.mainnet.chain.robinhood.com")
    RPC_BASE: str = os.getenv("RPC_BASE", "https://mainnet.base.org")
    RPC_SOLANA: str = os.getenv("RPC_SOLANA", "https://api.mainnet-beta.solana.com")

    # Platform URLs
    FOMO_BASE_URL: str = "https://fomo.family"
    FOMO_PROD_API: str = "https://prod-api.fomo.family"

    # Supported Chains mapping
    CHAINS: Dict[str, dict] = field(default_factory=lambda: {
        "robinhood": {
            "name": "Robinhood Chain",
            "symbol": "ROBINHOOD",
            "rpc": os.getenv("RPC_ROBINHOOD", "https://rpc.mainnet.chain.robinhood.com"),
            "explorer": "https://robinhoodchain.blockscout.com",
            "native_currency": "ETH",
            "native_price_estimate": 2500.0
        },
        "base": {
            "name": "Base Network",
            "symbol": "BASE",
            "rpc": os.getenv("RPC_BASE", "https://mainnet.base.org"),
            "explorer": "https://basescan.org",
            "native_currency": "ETH",
            "native_price_estimate": 2500.0
        },
        "solana": {
            "name": "Solana",
            "symbol": "SOL",
            "rpc": os.getenv("RPC_SOLANA", "https://api.mainnet-beta.solana.com"),
            "explorer": "https://solscan.io",
            "native_currency": "SOL",
            "native_price_estimate": 140.0
        }
    })

config = Config()
