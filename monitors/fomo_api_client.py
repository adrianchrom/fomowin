import asyncio
import logging
import urllib.request
import ssl
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from config import config

logger = logging.getLogger("FOMOApiClient")

# Known Native Quote Currencies across Solana, EVM & Robinhood Chain
QUOTE_CURRENCIES = {
    # Solana
    "so11111111111111111111111111111111111111112", # WSOL
    "epjfwdd5aufqssqem2qn1xzybapc8g4weggkzwytdt1v", # USDC (Solana)
    "es9vmfrzacermjfrf4h2fyd4conky11mcce8benwnybf", # USDT (Solana)
    # Base / Robinhood / EVM
    "0x4200000000000000000000000000000000000006", # WETH (Base)
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", # USDC (Base)
    "0x0bd7d308f8e1639fab988df18a8011f41eacad73", # WETH (Robinhood)
    "0x5317c0d077d2eeb639448939b930d49c4984b63b", # WBTC (Robinhood)
    "0x0000000000000000000000000000000000000000",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", # WETH (Ethereum)
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", # USDC (Ethereum)
    "0xdac17f958d2ee523a2206206994597c13d831ec7", # USDT (Ethereum)
}

class FOMOApiClient:
    """Client for interacting with GeckoTerminal New Pools API, DexScreener, and FOMO Family."""

    def __init__(self):
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://fomo.family/",
            "Accept": "application/json, text/plain, */*"
        }

    def get_fomo_url(self, chain: str, token_address: str) -> str:
        """Construct the direct FOMO trading URL preserving exact case sensitivity for Solana Base58."""
        clean_chain = chain.lower()
        clean_addr = token_address.strip()
        if clean_chain == "solana":
            return f"{config.FOMO_BASE_URL}/tokens/solana/{clean_addr}"
        elif clean_chain in ["base", "robinhood", "ethereum", "evm"]:
            return f"{config.FOMO_BASE_URL}/tokens/{clean_chain}/{clean_addr.lower()}"
        return f"{config.FOMO_BASE_URL}/tokens/{clean_chain}/{clean_addr}"

    async def fetch_geckoterminal_new_pools(self, chain_id: str) -> List[Dict[str, Any]]:
        """Fetch brand new pools (STRICTLY 0-30 minutes old) with correct target token identification."""
        url = f"https://api.geckoterminal.com/api/v2/networks/{chain_id}/new_pools"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            loop = asyncio.get_event_loop()

            def _fetch():
                with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            data = await loop.run_in_executor(None, _fetch)
            raw_pools = data.get("data", [])
            parsed_pools = []

            for p in raw_pools:
                attr = p.get("attributes", {})
                rel = p.get("relationships", {})
                
                # Extract base & quote token IDs preserving case sensitivity for Base58 (Solana)
                base_token_id = rel.get("base_token", {}).get("data", {}).get("id", "")
                quote_token_id = rel.get("quote_token", {}).get("data", {}).get("id", "")

                base_addr = base_token_id.split("_", 1)[1] if "_" in base_token_id else ""
                quote_addr = quote_token_id.split("_", 1)[1] if "_" in quote_token_id else ""

                if not base_addr and not quote_addr:
                    continue

                # Correctly identify NEW target token vs native quote currency (SOL/WETH/USDC)
                base_is_quote = base_addr.lower() in QUOTE_CURRENCIES
                quote_is_quote = quote_addr.lower() in QUOTE_CURRENCIES

                if base_is_quote and not quote_is_quote and quote_addr:
                    target_token_addr = quote_addr
                elif base_addr and not base_is_quote:
                    target_token_addr = base_addr
                else:
                    target_token_addr = quote_addr

                if not target_token_addr or target_token_addr.lower() in QUOTE_CURRENCIES:
                    continue

                # Calculate Age with strict ISO date parsing
                created_str = attr.get("pool_created_at")
                age_min = -1.0
                if created_str:
                    try:
                        # Clean ISO format in Python 3.9
                        clean_str = created_str.split(".")[0].rstrip("Z")
                        created_dt = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                        age_sec = (datetime.now(timezone.utc) - created_dt).total_seconds()
                        age_min = age_sec / 60.0
                    except Exception as e:
                        logger.debug(f"Failed to parse pool_created_at '{created_str}': {e}")
                        continue

                # Strict Filter: Discard token if age > 30 minutes or unverified!
                if age_min < 0 or age_min > config.MAX_NEW_TOKEN_AGE_MINUTES:
                    continue

                raw_name = attr.get("name", "Unknown Pool")
                symbol = raw_name
                # Parse correct symbol for target token
                if "/" in raw_name:
                    parts = [x.strip() for x in raw_name.split("/")]
                    if target_token_addr == quote_addr and len(parts) > 1:
                        symbol = parts[1]
                    else:
                        symbol = parts[0]
                pc_dict = attr.get("price_change_percentage") or {}
                pc5m = 0.0
                if isinstance(pc_dict, dict):
                    val = pc_dict.get("m5") or pc_dict.get("h1") or pc_dict.get("5m") or 0.0
                    try:
                        pc5m = float(val)
                    except (ValueError, TypeError):
                        pc5m = 0.0

                if not symbol or symbol in ["No data here", "Unknown Pool", "UNKNOWN", "null", "undefined"]:
                    symbol = f"TKN-{target_token_addr[:4].upper()}"

                name = f"{symbol} Token" if not symbol.endswith("Token") else symbol

                price_usd = float(attr.get("base_token_price_usd", 0) or 0)
                mc = float(attr.get("fdv_usd", 0) or attr.get("market_cap_usd", 0) or 0)
                liq = float(attr.get("reserve_in_usd", 0) or 0)

                # Fallback Market Cap calculation if FDV is not reported
                if mc == 0 and price_usd > 0:
                    mc = price_usd * 1_000_000_000
                elif mc == 0 and liq > 0:
                    mc = liq * 2

                parsed_pools.append({
                    "token_address": target_token_addr,
                    "symbol": symbol,
                    "name": name,
                    "chain": chain_id,
                    "pair_address": p.get("id", ""),
                    "price_usd": price_usd,
                    "market_cap": mc,
                    "liquidity_usd": liq,
                    "age_minutes": round(age_min, 1),
                    "price_change_5m": pc5m,
                    "fomo_url": self.get_fomo_url(chain_id, target_token_addr)
                })

            return parsed_pools
        except Exception as e:
            logger.debug(f"Failed to fetch GeckoTerminal new pools for {chain_id}: {e}")
            return []

fomo_client = FOMOApiClient()
