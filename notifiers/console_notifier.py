import logging
from typing import List
from monitors.new_token_scanner import TokenListing

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False

logger = logging.getLogger("ConsoleNotifier")

class ConsoleNotifier:
    """Provides formatted CLI terminal notifications and live updating tables."""

    def print_startup_banner(self):
        banner = """
=================================================================================
  🚀 FOMO WHALE & 0-30M PUMP SIGNAL BOT
=================================================================================
  Monitoring Chains       : Robinhood Chain, Base, Solana
  Strict Token Age Limit  : 0 to 30 MINUTES MAXIMUM ONLY
  Buy Investment Threshold: >= $5,000.00 USD
  Whale Portfolio Filter  : >= $500,000.00 USD Net Worth
  5m Pump Threshold       : +5,000% (50x) in < 5 minutes
  Mega Pump Threshold     : +20,000% (200x Parabolic Explosion)
  Web Dashboard           : http://localhost:8000
=================================================================================
        """
        if HAS_RICH:
            console.print(Panel(banner.strip(), title="⚡ BOT READY", style="bold green"))
        else:
            print(banner)

    def print_signal_alert(self, token: TokenListing, signal_info: dict):
        sig_type = signal_info.get("type", "")
        if sig_type == "mega_pump":
            msg = f"💥 MEGA PARABOLIC PUMP ALERT: {token.symbol} pumped +{signal_info.get('pump_pct', 0):,.0f}%!\nFOMO Link: {token.fomo_url}"
            style = "bold white on red"
        elif sig_type == "pump_5m":
            msg = f"🚀 5-MINUTE PUMP ALERT: {token.symbol} (< 5 min old) pumped +{signal_info.get('pump_pct', 0):,.0f}%!\nFOMO Link: {token.fomo_url}"
            style = "bold black on yellow"
        elif sig_type == "buy_5k":
            data = signal_info.get("data", {})
            msg = (
                f"💰 TRADER BUY ALERT ($5,000+ USD): {token.symbol}\n"
                f"Trader: {data.get('trader_username', 'Trader')} | Investment: ${data.get('amount_usd', 0):,.2f} USD\n"
                f"Opis / Thesis: '{data.get('trade_comment', '')}'\n"
                f"FOMO Link: {token.fomo_url}"
            )
            style = "bold black on gold1"
        else:
            whale_data = signal_info.get("data", {})
            msg = (
                f"🐋 WHALE BUY ALERT ($500k+ Portfolio): {token.symbol}\n"
                f"Trader: {whale_data.get('trader_username', 'Whale')} (${whale_data.get('portfolio_usd', 0):,.2f} USD)\n"
                f"Opis / Thesis: '{whale_data.get('trade_comment', '')}'\n"
                f"FOMO Link: {token.fomo_url}"
            )
            style = "bold white on blue"

        if HAS_RICH:
            console.print(Panel(msg, title="🔥 SIGNAL TRIGGERED", style=style))
        else:
            print(f"\n{msg}\n")

    def render_tokens_table(self, tokens: List[TokenListing]):
        if not HAS_RICH:
            print(f"\n--- ACTIVE MONITORED TOKENS ({len(tokens)}) ---")
            for t in tokens[:10]:
                print(f"[{t.chain.upper()}] {t.symbol} | 5m %: +{t.price_change_5m:.0f}% | Age: {t.age_minutes:.1f}m | Status: {t.signal_status}")
            return

        table = Table(title="🔥 MONITORED TOKENS (0-30 MIN AGE, $5k+ BUYS & PUMPS)", show_lines=True)
        table.add_column("Chain", style="cyan")
        table.add_column("Symbol", style="bold white")
        table.add_column("Name", style="dim")
        table.add_column("Age", style="yellow")
        table.add_column("5m Change %", justify="right", style="bold green")
        table.add_column("Price USD", justify="right", style="green")
        table.add_column("Market Cap", justify="right", style="magenta")
        table.add_column("Signal Status", style="bold white")
        table.add_column("FOMO Link", style="blue")

        for t in tokens[-15:]:
            status_text = t.signal_status
            if t.signal_status == "MEGA_PUMP_20000":
                status_text = "💥 MEGA PUMP +20000%"
            elif t.signal_status == "PUMP_5000_NEW":
                status_text = "🚀 PUMP +5000% (<5m)"
            elif t.signal_status == "BUY_5k_PLUS":
                status_text = "💰 BUY $5,000+"
            elif t.signal_status == "WHALE_INTEREST":
                status_text = "🐋 WHALE (> $500k)"

            table.add_row(
                t.chain.upper(),
                t.symbol,
                t.name[:20],
                f"{t.age_minutes:.1f}m",
                f"+{t.price_change_5m:,.0f}%",
                f"${t.price_usd:,.6f}",
                f"${t.market_cap:,.2f}",
                status_text,
                t.fomo_url
            )

        console.print(table)

console_notifier = ConsoleNotifier()
