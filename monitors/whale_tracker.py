import asyncio
import logging
import urllib.request
import ssl
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from config import config

logger = logging.getLogger("WhaleTracker")

@dataclass
class WhaleTransaction:
    tx_hash: str
    token_address: str
    token_symbol: str
    chain: str
    wallet_address: str
    portfolio_usd: float
    trade_type: str  # BUY / SELL / HOLD
    amount_usd: float
    timestamp: float
    fomo_url: str
    trader_username: str = ""   # Trader Username / Handle (e.g. @alpha_trader)
    trade_comment: str = ""     # Trade Description / Thesis provided upon buy

@dataclass
class TokenWhaleInterest:
    token_address: str
    token_symbol: str
    chain: str
    fomo_url: str
    total_whale_volume_usd: float = 0.0
    whale_buyer_count: int = 0
    whales: List[str] = field(default_factory=list)
    first_seen: float = 0.0
    last_signal_time: float = 0.0
    signal_triggered: bool = False

class WhaleTracker:
    """Monitors and evaluates wallet balances to identify Whales ($500k+ USD) and score interest."""

    def __init__(self):
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        self._wallet_cache: Dict[str, float] = {}
        self.token_interests: Dict[str, TokenWhaleInterest] = {}

    def get_rpc_url(self, chain: str) -> str:
        chain_cfg = config.CHAINS.get(chain.lower(), config.CHAINS["robinhood"])
        return chain_cfg["rpc"]

    async def get_wallet_net_worth(self, wallet_address: str, chain: str = "robinhood") -> float:
        """Fetch native balance + token balances to estimate wallet USD net worth."""
        wallet_key = f"{chain}:{wallet_address.lower()}"
        if wallet_key in self._wallet_cache:
            return self._wallet_cache[wallet_key]

        rpc_url = self.get_rpc_url(chain)
        chain_cfg = config.CHAINS.get(chain.lower(), config.CHAINS["robinhood"])
        native_price = chain_cfg.get("native_price_estimate", 2500.0)

        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [wallet_address, "latest"],
            "id": 1
        }).encode("utf-8")

        loop = asyncio.get_event_loop()

        def _query_rpc():
            req = urllib.request.Request(rpc_url, data=payload, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=5) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                result_hex = res.get("result", "0x0")
                wei = int(result_hex, 16)
                return (wei / 1e18) * native_price

        try:
            native_usd = await loop.run_in_executor(None, _query_rpc)
            self._wallet_cache[wallet_key] = native_usd
            return native_usd
        except Exception as e:
            logger.debug(f"Failed to fetch RPC balance for {wallet_address} on {chain}: {e}")
            return 0.0

    def is_whale(self, portfolio_usd: float) -> bool:
        """Check if portfolio meets the $500,000 threshold."""
        return portfolio_usd >= config.WHALE_MIN_PORTFOLIO_USD

    async def record_transaction(
        self,
        tx_hash: str,
        token_address: str,
        token_symbol: str,
        chain: str,
        wallet_address: str,
        amount_usd: float,
        trade_type: str = "BUY",
        fomo_url: str = "",
        trader_username: str = "",
        trade_comment: str = ""
    ) -> Optional[WhaleTransaction]:
        """Record a transaction, verify $5,000+ buy or $500k Whale status, and return WhaleTransaction if qualified."""
        portfolio_usd = await self.get_wallet_net_worth(wallet_address, chain)
        
        # Qualifies if either portfolio >= $500k OR buy amount >= $5,000 USD
        is_whale_wallet = self.is_whale(portfolio_usd)
        is_big_buy = amount_usd >= config.BUY_MIN_INVESTMENT_USD

        if not (is_whale_wallet or is_big_buy):
            return None

        # Fallback trader username formatting if not provided
        if not trader_username:
            trader_username = f"@{wallet_address[:6]}...{wallet_address[-4:]}"

        # Fallback trade comment / thesis formatting if not provided
        if not trade_comment:
            if is_whale_wallet:
                trade_comment = f"Apeing ${amount_usd:,.0f} USD into early token (Whale Balance: ${portfolio_usd:,.0f} USD) 🚀"
            else:
                trade_comment = f"BOUGHT ${amount_usd:,.0f} USD on early launch pool! 🔥"

        tx_event = WhaleTransaction(
            tx_hash=tx_hash,
            token_address=token_address.lower(),
            token_symbol=token_symbol,
            chain=chain.lower(),
            wallet_address=wallet_address.lower(),
            portfolio_usd=portfolio_usd,
            trade_type=trade_type,
            amount_usd=amount_usd,
            timestamp=asyncio.get_event_loop().time(),
            fomo_url=fomo_url,
            trader_username=trader_username,
            trade_comment=trade_comment
        )

        token_key = f"{chain.lower()}:{token_address.lower()}"
        if token_key not in self.token_interests:
            self.token_interests[token_key] = TokenWhaleInterest(
                token_address=token_address.lower(),
                token_symbol=token_symbol,
                chain=chain.lower(),
                fomo_url=fomo_url,
                first_seen=asyncio.get_event_loop().time()
            )

        interest = self.token_interests[token_key]
        interest.total_whale_volume_usd += amount_usd
        if wallet_address.lower() not in interest.whales:
            interest.whales.append(wallet_address.lower())
            interest.whale_buyer_count += 1

        logger.info(
            f"💰 BUY SIGNAL DETECTED ({chain.upper()})! Trader {trader_username} "
            f"bought ${amount_usd:,.2f} of {token_symbol} | Thesis: '{trade_comment}'"
        )

        return tx_event

whale_tracker = WhaleTracker()
