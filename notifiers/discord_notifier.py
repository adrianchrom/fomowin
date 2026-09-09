import asyncio
import logging
import urllib.request
import ssl
import json
from config import config
from monitors.new_token_scanner import TokenListing

logger = logging.getLogger("DiscordNotifier")

class DiscordNotifier:
    """Sends rich Discord embed alerts for $5k+ buys, trader theses, 5m Pumps (+5000%), Mega Pumps (+20000%), and Whales (> $500k)."""

    def __init__(self):
        self.webhook_url = config.DISCORD_WEBHOOK_URL
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

    async def send_signal_alert(self, token: TokenListing, signal_info: dict):
        if not self.webhook_url:
            return

        sig_type = signal_info.get("type", "")
        if sig_type == "mega_pump":
            title = f"💥 MEGA PARABOLIC PUMP: {token.symbol} (+{signal_info.get('pump_pct', 0):,.0f}%)"
            desc = f"Token skyrocketed **+{signal_info.get('pump_pct', 0):,.0f}%**!"
            color = 0xFF0055
            fields = []
        elif sig_type == "pump_5m":
            title = f"🚀 5-MINUTE PUMP: {token.symbol} (+{signal_info.get('pump_pct', 0):,.0f}%)"
            desc = f"New coin (< 5 min old) pumped **+{signal_info.get('pump_pct', 0):,.0f}%**!"
            color = 0x00FF88
            fields = []
        elif sig_type == "buy_5k":
            data = signal_info.get("data", {})
            title = f"💰 TRADER BUY SIGNAL ($5,000+ USD): {token.symbol}"
            desc = f"Trader **{data.get('trader_username', 'Trader')}** invested **${data.get('amount_usd', 0):,.2f} USD**!"
            color = 0xFBBF24
            fields = [
                {"name": "👤 Trader Username", "value": f"`{data.get('trader_username', 'Trader')}`", "inline": True},
                {"name": "💬 Opis / Thesis", "value": f"*{data.get('trade_comment', '')}*", "inline": False}
            ]
        else:
            whale_data = signal_info.get("data", {})
            title = f"🐋 WHALE BUY SIGNAL: {token.symbol} ({token.chain.upper()})"
            desc = f"Whale **{whale_data.get('trader_username', 'Whale')}** (${whale_data.get('portfolio_usd', 0):,.2f} USD) entered token!"
            color = 0x00CCFF
            fields = [
                {"name": "👤 Trader / Whale", "value": f"`{whale_data.get('trader_username', 'Whale')}`", "inline": True},
                {"name": "💬 Opis / Thesis", "value": f"*{whale_data.get('trade_comment', '')}*", "inline": False}
            ]

        base_fields = [
            {"name": "🪙 Token Symbol", "value": f"`{token.symbol}`", "inline": True},
            {"name": "🌐 Network", "value": token.chain.upper(), "inline": True},
            {"name": "⏱️ Token Age", "value": f"{token.age_minutes:.1f} min", "inline": True},
            {"name": "💵 Price USD", "value": f"${token.price_usd:,.6f}", "inline": True},
            {"name": "📊 Market Cap", "value": f"${token.market_cap:,.2f}", "inline": True},
            {"name": "🔗 Trade on FOMO Family", "value": f"[Open FOMO Page]({token.fomo_url})", "inline": False}
        ]

        embed = {
            "title": title,
            "description": desc,
            "url": token.fomo_url,
            "color": color,
            "fields": fields + base_fields,
            "footer": {"text": "FOMO Whale & 0-30m Pump Bot"}
        }

        payload = json.dumps({"embeds": [embed]}).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        loop = asyncio.get_event_loop()

        def _send():
            req = urllib.request.Request(self.webhook_url, data=payload, headers=headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as resp:
                return resp.read().decode("utf-8")

        try:
            await loop.run_in_executor(None, _send)
        except Exception as e:
            logger.error(f"Failed to send Discord webhook alert: {e}")

discord_notifier = DiscordNotifier()
