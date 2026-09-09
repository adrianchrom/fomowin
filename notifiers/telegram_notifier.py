import asyncio
import logging
import urllib.request
import ssl
import json
from config import config
from monitors.new_token_scanner import TokenListing

logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    """Sends formatted Telegram alerts for $5k+ buys, trader theses, 5m Pumps (+5000%), Mega Pumps (+20000%), and Whales (> $500k)."""

    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

    async def send_signal_alert(self, token: TokenListing, signal_info: dict):
        if not self.bot_token or not self.chat_id:
            return

        sig_type = signal_info.get("type", "")
        if sig_type == "mega_pump":
            title = "💥 <b>MEGA PARABOLIC PUMP ALERT (+20,000%)</b> 💥"
            sub = f"🚀 <b>5m Price Increase:</b> +{signal_info.get('pump_pct', 0):,.0f}%"
        elif sig_type == "pump_5m":
            title = "🚀 <b>5-MINUTE PUMP ALERT (+5,000% IN &lt; 5 MIN)</b> 🚀"
            sub = f"⚡ <b>5m Price Increase:</b> +{signal_info.get('pump_pct', 0):,.0f}% | ⏱️ <b>Token Age:</b> {token.age_minutes:.1f}m"
        elif sig_type == "buy_5k":
            data = signal_info.get("data", {})
            title = "💰 <b>TRADER BUY SIGNAL (&gt; $5,000 USD)</b> 💰"
            sub = (
                f"👤 <b>Trader Username:</b> <code>{data.get('trader_username', 'Trader')}</code>\n"
                f"📥 <b>Investment Amount:</b> <b>${data.get('amount_usd', 0):,.2f} USD</b>\n"
                f"💬 <b>Opis / Thesis:</b> <i>\"{data.get('trade_comment', '')}\"</i>"
            )
        else:
            whale_data = signal_info.get("data", {})
            title = "🐋 <b>WHALE BUY SIGNAL (&gt; $500,000 USD PORTFOLIO)</b> 🐋"
            sub = (
                f"👤 <b>Trader / Whale:</b> <code>{whale_data.get('trader_username', 'Whale')}</code>\n"
                f"💰 <b>Portfolio Value:</b> <b>${whale_data.get('portfolio_usd', 0):,.2f} USD</b>\n"
                f"💬 <b>Opis / Thesis:</b> <i>\"{whale_data.get('trade_comment', '')}\"</i>"
            )

        message = (
            f"{title}\n\n"
            f"🪙 <b>Coin:</b> <code>{token.symbol}</code> ({token.name})\n"
            f"🌐 <b>Chain:</b> {token.chain.upper()}\n"
            f"⏱️ <b>Wiek Tokena:</b> {token.age_minutes:.1f} min (&le; 30 min)\n"
            f"💵 <b>Price:</b> ${token.price_usd:,.6f}\n"
            f"📊 <b>Market Cap:</b> ${token.market_cap:,.2f}\n"
            f"{sub}\n\n"
            f"🔗 <b>FOMO Platform Link:</b>\n"
            f"<a href='{token.fomo_url}'>{token.fomo_url}</a>\n"
        )

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        loop = asyncio.get_event_loop()

        def _send():
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=8) as resp:
                return resp.read().decode("utf-8")

        try:
            await loop.run_in_executor(None, _send)
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

telegram_notifier = TelegramNotifier()
