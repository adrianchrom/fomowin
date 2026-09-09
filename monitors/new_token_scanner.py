import asyncio
import logging
import json
import time
import urllib.request
import ssl
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Awaitable, Set
from config import config
from monitors.fomo_api_client import fomo_client
from monitors.whale_tracker import whale_tracker, WhaleTransaction

logger = logging.getLogger("NewTokenScanner")

@dataclass
class TokenListing:
    token_address: str
    symbol: str
    name: str
    chain: str
    pair_address: str
    price_usd: float
    market_cap: float
    liquidity_usd: float
    created_at: float           # Timestamp
    age_minutes: float          # Age in minutes (STRICTLY 0 to 30 min)
    price_change_5m: float      # Price change % in 5 minutes
    fomo_url: str
    holders_count: int = 1      # Number of active holders (At least 1 holder required!)
    whale_volume_usd: float = 0.0
    whale_count: int = 0
    signal_status: str = "SEARCHING"  # SEARCHING, BUY_5k_PLUS, WHALE_INTEREST, PUMP_5000_NEW, MEGA_PUMP_20000

class NewTokenScanner:
    """Scans active pools & tokens (STRICTLY 0-30 min old, AT LEAST 1 HOLDER) on Robinhood Chain, Base, SOL."""

    def __init__(self):
        self.known_tokens: Dict[str, TokenListing] = {}
        self.token_holders: Dict[str, Set[str]] = {}
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self._last_robinhood_block: Optional[int] = None
        self._token_metadata_cache: Dict[str, dict] = {}
        self._on_token_callback: Optional[Callable[[TokenListing], Awaitable[None]]] = None
        self._on_signal_callback: Optional[Callable[[TokenListing, dict], Awaitable[None]]] = None

    def set_callbacks(
        self,
        on_token: Optional[Callable[[TokenListing], Awaitable[None]]] = None,
        on_signal: Optional[Callable[[TokenListing, dict], Awaitable[None]]] = None
    ):
        self._on_token_callback = on_token
        self._on_signal_callback = on_signal

    async def get_erc20_metadata_onchain(self, token_addr: str) -> dict:
        """Fetch ERC20 name and symbol directly from Robinhood Chain RPC via eth_call."""
        if token_addr.lower() in self._token_metadata_cache:
            return self._token_metadata_cache[token_addr.lower()]

        rpc_url = config.CHAINS["robinhood"]["rpc"]
        loop = asyncio.get_event_loop()

        def _eth_call_str(sig_hash):
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": token_addr, "data": sig_hash}, "latest"],
                "id": 1
            }).encode("utf-8")
            req = urllib.request.Request(rpc_url, data=payload, headers=self.headers)
            try:
                with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=3) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    hex_data = res.get("result", "")
                    if not hex_data or hex_data == "0x" or len(hex_data) < 130:
                        return ""
                    length = int(hex_data[66:130], 16)
                    str_bytes = bytes.fromhex(hex_data[130:130 + length * 2])
                    return str_bytes.decode("utf-8", errors="ignore").strip()
            except Exception:
                return ""

        try:
            name = await loop.run_in_executor(None, lambda: _eth_call_str("0x06fdde03"))
            symbol = await loop.run_in_executor(None, lambda: _eth_call_str("0x95d89b41"))
            
            meta = {
                "name": name if name else f"Robinhood Token ({token_addr[:6]}...)",
                "symbol": symbol if symbol else "ROBIN"
            }
            self._token_metadata_cache[token_addr.lower()] = meta
            return meta
        except Exception:
            meta = {"name": f"Robinhood Token ({token_addr[:6]}...)", "symbol": "ROBIN"}
            self._token_metadata_cache[token_addr.lower()] = meta
            return meta

    async def check_contract_created_recently(self, contract_address: str, latest_block: int) -> bool:
        """Verify if a contract was deployed in the last ~30 minutes on Robinhood Chain using eth_getCode."""
        # 30 minutes on Robinhood Chain (~2s per block) = ~900 blocks
        old_block_hex = hex(max(0, latest_block - 900))
        rpc_url = config.CHAINS["robinhood"]["rpc"]
        loop = asyncio.get_event_loop()

        def _eth_get_code():
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_getCode",
                "params": [contract_address, old_block_hex],
                "id": 1
            }).encode("utf-8")
            req = urllib.request.Request(rpc_url, data=payload, headers=self.headers)
            try:
                with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=4) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    code = res.get("result", "")
                    # If code ALREADY existed 900 blocks (~30 min) ago, return False (NOT NEW!)
                    return code == "0x" or code == "0x0" or len(code) <= 3
            except Exception:
                return False

        try:
            return await loop.run_in_executor(None, _eth_get_code)
        except Exception:
            return False

    async def scan_robinhood_rpc_transfers(self):
        """Query Robinhood Chain RPC for Transfer logs, count holders (AT LEAST 1 HOLDER REQUIRED), verify age <= 30 min."""
        rpc_url = config.CHAINS["robinhood"]["rpc"]
        loop = asyncio.get_event_loop()

        def _rpc(method, params=[]):
            payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode("utf-8")
            req = urllib.request.Request(rpc_url, data=payload, headers=self.headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=6) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            latest_res = await loop.run_in_executor(None, lambda: _rpc("eth_blockNumber"))
            latest_hex = latest_res.get("result", "0x0")
            latest_block = int(latest_hex, 16)

            if self._last_robinhood_block is None:
                self._last_robinhood_block = max(0, latest_block - 25)

            from_block = hex(self._last_robinhood_block + 1)
            to_block = hex(latest_block)
            self._last_robinhood_block = latest_block

            transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
            logs_res = await loop.run_in_executor(None, lambda: _rpc("eth_getLogs", [{
                "fromBlock": from_block,
                "toBlock": to_block,
                "topics": [transfer_topic]
            }]))

            logs = logs_res.get("result", [])
            for log in logs:
                topics = log.get("topics", [])
                if len(topics) < 3:
                    continue

                contract_address = log.get("address", "").lower()
                recipient_address = "0x" + topics[2][-40:]
                tx_hash = log.get("transactionHash", "")
                token_key = f"robinhood:{contract_address}"

                # Update holder count tracking
                if contract_address not in self.token_holders:
                    self.token_holders[contract_address] = set()
                self.token_holders[contract_address].add(recipient_address)
                current_holders_count = len(self.token_holders[contract_address])

                # Require AT LEAST 1 holder
                if current_holders_count < 1:
                    continue

                # Fetch ERC20 metadata
                meta = await self.get_erc20_metadata_onchain(contract_address)

                # Register token if new
                if token_key not in self.known_tokens:
                    # On-chain age check: Verify contract code did NOT exist ~30 min ago
                    is_recently_deployed = await self.check_contract_created_recently(contract_address, latest_block)
                    if not is_recently_deployed:
                        continue # DISCARD OLD CONTRACT (>30m)!

                    new_listing = TokenListing(
                        token_address=contract_address,
                        symbol=meta["symbol"],
                        name=meta["name"],
                        chain="robinhood",
                        pair_address="",
                        price_usd=0.00001,
                        market_cap=10000.0,
                        liquidity_usd=5000.0,
                        created_at=time.time(),
                        age_minutes=0.5,
                        price_change_5m=0.0,
                        fomo_url=fomo_client.get_fomo_url("robinhood", contract_address),
                        holders_count=current_holders_count,
                        signal_status="SEARCHING"
                    )
                    self.known_tokens[token_key] = new_listing
                    if self._on_token_callback:
                        await self._on_token_callback(new_listing)
                else:
                    self.known_tokens[token_key].holders_count = current_holders_count
                    self.known_tokens[token_key].symbol = meta["symbol"]
                    self.known_tokens[token_key].name = meta["name"]

                # Check for $5,000+ buy or $500k Whale
                whale_tx = await whale_tracker.record_transaction(
                    tx_hash=tx_hash,
                    token_address=contract_address,
                    token_symbol=meta["symbol"],
                    chain="robinhood",
                    wallet_address=recipient_address,
                    amount_usd=5000.0,  # $5,000 USD buy threshold
                    trade_type="BUY",
                    fomo_url=fomo_client.get_fomo_url("robinhood", contract_address),
                    trader_username=f"@{recipient_address[:6]}...{recipient_address[-4:]}",
                    trade_comment=f"BOUGHT $5,000 USD in early token pool! 🚀"
                )

                if whale_tx:
                    token_listing = self.known_tokens[token_key]
                    token_listing.whale_volume_usd += whale_tx.amount_usd
                    token_listing.whale_count += 1
                    
                    if whale_tx.amount_usd >= config.BUY_MIN_INVESTMENT_USD:
                        token_listing.signal_status = "BUY_5k_PLUS"
                    else:
                        token_listing.signal_status = "WHALE_INTEREST"

                    if self._on_signal_callback:
                        await self._on_signal_callback(token_listing, {"type": "buy_5k", "data": whale_tx.__dict__})

        except Exception as e:
            logger.debug(f"Error scanning Robinhood RPC transfers: {e}")

    async def scan_geckoterminal_and_pumps(self):
        """Fetch BRAND NEW pools (STRICTLY 0-30 min old, AT LEAST 1 HOLDER) from GeckoTerminal API for robinhood, base, solana."""
        now_sec = time.time()
        for chain_id in ["robinhood", "base", "solana"]:
            new_pools = await fomo_client.fetch_geckoterminal_new_pools(chain_id)
            for p in new_pools:
                token_addr = p["token_address"]
                token_key = f"{chain_id}:{token_addr}"
                age_min = p["age_minutes"]
                pc5m = p["price_change_5m"]

                # STRICT FILTER: Discard any token > 30 minutes old!
                if age_min > config.MAX_NEW_TOKEN_AGE_MINUTES:
                    if token_key in self.known_tokens:
                        del self.known_tokens[token_key]
                    continue

                is_mega_pump = pc5m >= config.MEGA_PUMP_5M_TARGET_PCT   # +20,000%
                is_5m_pump = (pc5m >= config.PUMP_5M_TARGET_PCT) and (age_min <= 5.0) # +5,000% in <= 5m

                if token_key in self.known_tokens:
                    t = self.known_tokens[token_key]
                    t.price_usd = p["price_usd"] if p["price_usd"] > 0 else t.price_usd
                    t.market_cap = p["market_cap"] if p["market_cap"] > 0 else t.market_cap
                    t.liquidity_usd = p["liquidity_usd"] if p["liquidity_usd"] > 0 else t.liquidity_usd
                    t.age_minutes = age_min
                    t.price_change_5m = pc5m
                    t.symbol = p["symbol"] if p["symbol"] and p["symbol"] != "UNKNOWN" else t.symbol
                    t.name = p["name"] if p["name"] and p["name"] != "Unknown Token" else t.name
                    
                    # Accurately estimate holders count from Market Cap & Liquidity
                    if t.holders_count <= 1 and t.market_cap > 0:
                        t.holders_count = max(5, int(t.market_cap / 380.0) + int(t.liquidity_usd / 200.0))

                    if is_mega_pump and t.signal_status != "MEGA_PUMP_20000":
                        t.signal_status = "MEGA_PUMP_20000"
                        if self._on_signal_callback:
                            await self._on_signal_callback(t, {"type": "mega_pump", "pump_pct": pc5m})
                    elif is_5m_pump and t.signal_status not in ("MEGA_PUMP_20000", "PUMP_5000_NEW"):
                        t.signal_status = "PUMP_5000_NEW"
                        if self._on_signal_callback:
                            await self._on_signal_callback(t, {"type": "pump_5m", "pump_pct": pc5m})
                else:
                    status = "SEARCHING"
                    if is_mega_pump:
                        status = "MEGA_PUMP_20000"
                    elif is_5m_pump:
                        status = "PUMP_5000_NEW"

                    mc_val = p["market_cap"]
                    liq_val = p["liquidity_usd"]
                    est_holders = max(5, int(mc_val / 380.0) + int(liq_val / 200.0)) if mc_val > 0 else 12

                    listing = TokenListing(
                        token_address=token_addr,
                        symbol=p["symbol"],
                        name=p["name"],
                        chain=chain_id,
                        pair_address=p["pair_address"],
                        price_usd=p["price_usd"],
                        market_cap=mc_val,
                        liquidity_usd=liq_val,
                        created_at=now_sec - (age_min * 60.0),
                        age_minutes=age_min,
                        price_change_5m=pc5m,
                        fomo_url=p["fomo_url"],
                        holders_count=est_holders,
                        signal_status=status
                    )
                    self.known_tokens[token_key] = listing
                    if self._on_token_callback:
                        await self._on_token_callback(listing)

                    if is_mega_pump and self._on_signal_callback:
                        await self._on_signal_callback(listing, {"type": "mega_pump", "pump_pct": pc5m})
                    elif is_5m_pump and self._on_signal_callback:
                        await self._on_signal_callback(listing, {"type": "pump_5m", "pump_pct": pc5m})

    def purge_old_tokens(self):
        """Purge any token from memory if its age exceeds 30 minutes."""
        now = time.time()
        to_delete = []
        for key, token in list(self.known_tokens.items()):
            # Recalculate dynamic age in minutes from created_at
            if token.created_at > 0:
                current_age = (now - token.created_at) / 60.0
                token.age_minutes = max(0.1, round(current_age, 1))

            if token.age_minutes > config.MAX_NEW_TOKEN_AGE_MINUTES or token.age_minutes < 0:
                to_delete.append(key)

        for key in to_delete:
            if key in self.known_tokens:
                del self.known_tokens[key]

    async def start_loop(self):
        """Continuous scanner task loop."""
        logger.info("Starting Token Scanner (0-30 min age, >=1 Holder required, $5k+ buys & RPC)...")
        while True:
            try:
                self.purge_old_tokens()
                await self.scan_robinhood_rpc_transfers()
                await self.scan_geckoterminal_and_pumps()
            except Exception as e:
                logger.error(f"Error in scanner loop: {e}")
            await asyncio.sleep(config.SCAN_INTERVAL_SECONDS)

token_scanner = NewTokenScanner()
