import uuid
import time
from typing import List, Dict, Any, Optional

from monitors.storage import LOCK, data_path, atomic_write_json, load_json_file

ALERTS_FILE = data_path("DATA_ALERTS.json")


class MarketCapAlert:
    def __init__(self, token_name: str, ticker: str, ca: str, alert_type: str, target_mcap_usd: float, initial_mcap_usd: float = 0.0, fomo_url: str = "", owner: str = ""):
        self.id = str(uuid.uuid4())[:8]
        self.owner = owner or ""
        self.token_name = token_name
        self.ticker = ticker
        self.ca = ca
        self.alert_type = alert_type  # "BUY_UNDER" or "SELL_OVER"
        self.target_mcap_usd = target_mcap_usd
        self.initial_mcap_usd = initial_mcap_usd
        self.fomo_url = fomo_url or (f"https://fomo.family/tokens/solana/{ca}" if len(ca) < 40 else f"https://fomo.family/tokens/robinhood/{ca}")
        self.triggered = False
        self.created_at = time.time()
        self.triggered_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner": self.owner,
            "token_name": self.token_name,
            "ticker": self.ticker,
            "ca": self.ca,
            "alert_type": self.alert_type,
            "target_mcap_usd": self.target_mcap_usd,
            "initial_mcap_usd": self.initial_mcap_usd,
            "fomo_url": self.fomo_url,
            "triggered": self.triggered,
            "created_at": self.created_at,
            "triggered_at": self.triggered_at
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MarketCapAlert":
        alert = cls(
            token_name=d.get("token_name", "Token"),
            ticker=d.get("ticker", "TOKEN"),
            ca=d.get("ca", ""),
            alert_type=d.get("alert_type", "BUY_UNDER"),
            target_mcap_usd=float(d.get("target_mcap_usd", 0.0)),
            initial_mcap_usd=float(d.get("initial_mcap_usd", 0.0)),
            fomo_url=d.get("fomo_url", ""),
            owner=d.get("owner", ""),
        )
        alert.id = d.get("id", alert.id)
        alert.triggered = bool(d.get("triggered", False))
        alert.created_at = d.get("created_at", alert.created_at)
        alert.triggered_at = d.get("triggered_at")
        return alert


class AlertsManager:
    """Market-cap alerts. Every alert belongs to the user that created it and survives restarts."""

    def __init__(self):
        raw = load_json_file(ALERTS_FILE, [], lambda d: isinstance(d, list))
        self.alerts: Dict[str, MarketCapAlert] = {}
        for item in raw:
            try:
                alert = MarketCapAlert.from_dict(item)
                self.alerts[alert.id] = alert
            except Exception:
                continue

    def _persist(self):
        atomic_write_json(ALERTS_FILE, [a.to_dict() for a in self.alerts.values()])

    def add_alert(self, token_name: str, ticker: str, ca: str, alert_type: str, target_mcap_usd: float, current_mcap_usd: float = 0.0, fomo_url: str = "", owner: str = "") -> Dict[str, Any]:
        alert = MarketCapAlert(
            token_name=token_name or "Token",
            ticker=ticker or "TOKEN",
            ca=ca,
            alert_type=alert_type,
            target_mcap_usd=float(target_mcap_usd),
            initial_mcap_usd=float(current_mcap_usd),
            fomo_url=fomo_url,
            owner=owner
        )
        with LOCK:
            self.alerts[alert.id] = alert
            self._persist()
        return alert.to_dict()

    def remove_alert(self, alert_id: str, owner: Optional[str] = None) -> bool:
        with LOCK:
            alert = self.alerts.get(alert_id)
            if not alert:
                return False
            if owner is not None and alert.owner and alert.owner.lower() != owner.lower():
                return False  # somebody else's alert
            del self.alerts[alert_id]
            self._persist()
            return True

    def get_all_alerts(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            a.to_dict() for a in self.alerts.values()
            if owner is None or not a.owner or a.owner.lower() == owner.lower()
        ]

    def check_triggers(self, ca: str, current_mcap_usd: float) -> List[Dict[str, Any]]:
        triggered_list = []
        changed = False
        for alert in self.alerts.values():
            if not alert.triggered and alert.ca.lower() == ca.lower():
                if alert.alert_type == "BUY_UNDER" and current_mcap_usd <= alert.target_mcap_usd:
                    alert.triggered = True
                    alert.triggered_at = time.time()
                    triggered_list.append(alert.to_dict())
                    changed = True
                elif alert.alert_type == "SELL_OVER" and current_mcap_usd >= alert.target_mcap_usd:
                    alert.triggered = True
                    alert.triggered_at = time.time()
                    triggered_list.append(alert.to_dict())
                    changed = True
        if changed:
            self._persist()
        return triggered_list

alerts_manager = AlertsManager()
