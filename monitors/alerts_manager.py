import uuid
import time
from typing import List, Dict, Any, Optional

class MarketCapAlert:
    def __init__(self, token_name: str, ticker: str, ca: str, alert_type: str, target_mcap_usd: float, initial_mcap_usd: float = 0.0):
        self.id = str(uuid.uuid4())[:8]
        self.token_name = token_name
        self.ticker = ticker
        self.ca = ca
        self.alert_type = alert_type  # "BUY_UNDER" or "SELL_OVER"
        self.target_mcap_usd = target_mcap_usd
        self.initial_mcap_usd = initial_mcap_usd
        self.triggered = False
        self.created_at = time.time()
        self.triggered_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "token_name": self.token_name,
            "ticker": self.ticker,
            "ca": self.ca,
            "alert_type": self.alert_type,
            "target_mcap_usd": self.target_mcap_usd,
            "initial_mcap_usd": self.initial_mcap_usd,
            "triggered": self.triggered,
            "created_at": self.created_at,
            "triggered_at": self.triggered_at
        }

class AlertsManager:
    def __init__(self):
        self.alerts: Dict[str, MarketCapAlert] = {}
        # Pre-seed with a sample alert for demonstration
        sample = MarketCapAlert(
            token_name="Unipcs Runner",
            ticker="RUNNER",
            ca="7xKXtg2CW87d97TXJSD9...",
            alert_type="BUY_UNDER",
            target_mcap_usd=50000.0,
            initial_mcap_usd=120000.0
        )
        self.alerts[sample.id] = sample

    def add_alert(self, token_name: str, ticker: str, ca: str, alert_type: str, target_mcap_usd: float, current_mcap_usd: float = 0.0) -> Dict[str, Any]:
        alert = MarketCapAlert(
            token_name=token_name or "Token",
            ticker=ticker or "TOKEN",
            ca=ca,
            alert_type=alert_type,
            target_mcap_usd=float(target_mcap_usd),
            initial_mcap_usd=float(current_mcap_usd)
        )
        self.alerts[alert.id] = alert
        return alert.to_dict()

    def remove_alert(self, alert_id: str) -> bool:
        if alert_id in self.alerts:
            del self.alerts[alert_id]
            return True
        return False

    def get_all_alerts(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self.alerts.values()]

    def check_triggers(self, ca: str, current_mcap_usd: float) -> List[Dict[str, Any]]:
        triggered_list = []
        for alert in self.alerts.values():
            if not alert.triggered and alert.ca.lower() == ca.lower():
                if alert.alert_type == "BUY_UNDER" and current_mcap_usd <= alert.target_mcap_usd:
                    alert.triggered = True
                    alert.triggered_at = time.time()
                    triggered_list.append(alert.to_dict())
                elif alert.alert_type == "SELL_OVER" and current_mcap_usd >= alert.target_mcap_usd:
                    alert.triggered = True
                    alert.triggered_at = time.time()
                    triggered_list.append(alert.to_dict())
        return triggered_list

alerts_manager = AlertsManager()
