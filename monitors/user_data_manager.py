import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("UserDataManager")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PERMISSIONS_FILE = os.path.join(BASE_DIR, "USER_PERMISSIONS.json")
WYDATKI_FILE = os.path.join(BASE_DIR, "DATA_WYDATKI.json")
WYCENY_FILE = os.path.join(BASE_DIR, "DATA_WYCENY.json")
COMPANY_FILE = os.path.join(BASE_DIR, "DATA_COMPANY.json")

DEFAULT_PERMISSIONS = {
    "Adrian": {
        "fomo": True,
        "wydatki": True,
        "wyceny": True,
        "stopki_email": True,
        "is_admin": True
    },
    "Maciek": {
        "fomo": True,
        "wydatki": False,
        "wyceny": False,
        "stopki_email": False,
        "is_admin": False
    }
}

DEFAULT_COMPANY = {
    "Adrian": {
        "name": "Van Stev Sp. z o.o. Sp. k.",
        "address": "ul. Prosta 20, 00-001 Warszawa",
        "nip": "8992782026",
        "phone": "+48 605 595 049",
        "email": "adrian.chrom@gmail.com",
        "bank": "00 1234 5678 9012 3456 7890 1234",
        "logo_base64": ""
    },
    "Maciek": {
        "name": "MHF Trading Group",
        "address": "Rynek Główny 1, 30-001 Kraków",
        "nip": "1234567890",
        "phone": "+48 500 123 456",
        "email": "maciek@fomo.win",
        "bank": "11 2222 3333 4444 5555 6666 7777",
        "logo_base64": ""
    }
}

DEFAULT_WYDATKI = {
    "Adrian": [
        {
            "id": "wyd-101",
            "type": "PRZYCHÓD",
            "title": "Realizacja Wdrożenia FOMO Platform",
            "category": "Usługi",
            "amount_pln": 14500.0,
            "date": "2026-09-12",
            "note": "Płatność końcowa za moduł analizy ryzyka"
        },
        {
            "id": "wyd-102",
            "type": "WYDATEK",
            "title": "Hosting Cloud & Node Infrastructure",
            "category": "Biuro/Sprzęt",
            "amount_pln": 1250.0,
            "date": "2026-09-10",
            "note": "Opłata za serwery RPC Solana & Base"
        }
    ],
    "Maciek": [
        {
            "id": "wyd-201",
            "type": "PRZYCHÓD",
            "title": "Konsultacje Sygnałowe Krypto",
            "category": "Krypto/Inwestycje",
            "amount_pln": 3200.0,
            "date": "2026-09-14",
            "note": "Płatność za doradztwo on-chain"
        }
    ]
}

DEFAULT_WYCENY = {
    "Adrian": [
        {
            "id": "wyc-101",
            "client_name": "Crypto Fund Alpha",
            "project_title": "Dedykowany Bot Sygnałowy FOMO Engine",
            "items": [
                {"description": "Moduł skanera 0-30m", "qty": 1, "unit_price": 8000.0},
                {"description": "Integracja RPC & Insiders Feed", "qty": 1, "unit_price": 4500.0}
            ],
            "tax_rate": 23.0,
            "total_netto": 12500.0,
            "total_brutto": 15375.0,
            "status": "Zaakceptowano",
            "date": "2026-09-11",
            "notes": "Warunki płatności 50/50"
        }
    ],
    "Maciek": [
        {
            "id": "wyc-201",
            "client_name": "MHF Trading Group",
            "project_title": "Audyt Bezpieczeństwa Kontraktów CA",
            "items": [
                {"description": "Analiza Honeypot & Anti-rug", "qty": 1, "unit_price": 3500.0}
            ],
            "tax_rate": 23.0,
            "total_netto": 3500.0,
            "total_brutto": 4305.0,
            "status": "Wysłano do Klienta",
            "date": "2026-09-13",
            "notes": "Oczekuje na akceptację dyrektora"
        }
    ]
}

class UserDataManager:
    """Manages persistent JSON storage & strict privacy isolation per user."""

    def __init__(self):
        self.permissions = self._load_json(PERMISSIONS_FILE, DEFAULT_PERMISSIONS)
        self.wydatki = self._load_json(WYDATKI_FILE, DEFAULT_WYDATKI)
        self.wyceny = self._load_json(WYCENY_FILE, DEFAULT_WYCENY)
        self.company = self._load_json(COMPANY_FILE, DEFAULT_COMPANY)

    def _load_json(self, filepath: str, default_data: dict) -> dict:
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {filepath}: {e}")
        self._save_json(filepath, default_data)
        return dict(default_data)

    def _save_json(self, filepath: str, data: dict):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving {filepath}: {e}")

    # PERMISSIONS MANAGEMENT
    def get_user_permissions(self, username: str) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else ("Maciek" if username.lower() == "maciek" else username)
        if canonical not in self.permissions:
            self.permissions[canonical] = {
                "fomo": True,
                "wydatki": False,
                "wyceny": False,
                "stopki_email": False,
                "is_admin": False
            }
            self._save_json(PERMISSIONS_FILE, self.permissions)
        
        # Adrian always retains super admin access
        if canonical == "Adrian":
            return {
                "fomo": True,
                "wydatki": True,
                "wyceny": True,
                "stopki_email": True,
                "is_admin": True
            }
        return self.permissions[canonical]

    def update_maciek_permissions(self, new_perms: dict) -> dict:
        target = "Maciek"
        if target not in self.permissions:
            self.permissions[target] = {}
        
        for k in ["wydatki", "wyceny", "stopki_email"]:
            if k in new_perms:
                self.permissions[target][k] = bool(new_perms[k])
        
        self.permissions[target]["fomo"] = True
        self.permissions[target]["is_admin"] = False
        self._save_json(PERMISSIONS_FILE, self.permissions)
        return self.permissions[target]

    # WYDATKI DATA (STRICT PER-USER ISOLATION)
    def get_user_wydatki(self, username: str) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        return self.wydatki.get(canonical, [])

    def add_user_wydatki(self, username: str, entry: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        if canonical not in self.wydatki:
            self.wydatki[canonical] = []
        
        entry["id"] = f"wyd-{len(self.wydatki[canonical]) + 101}"
        self.wydatki[canonical].insert(0, entry)
        self._save_json(WYDATKI_FILE, self.wydatki)
        return entry

    def delete_user_wydatki(self, username: str, entry_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        items = self.wydatki.get(canonical, [])
        filtered = [x for x in items if x.get("id") != entry_id]
        if len(filtered) < len(items):
            self.wydatki[canonical] = filtered
            self._save_json(WYDATKI_FILE, self.wydatki)
            return True
        return False

    # WYCENY DATA (STRICT PER-USER ISOLATION)
    def get_user_wyceny(self, username: str) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        return self.wyceny.get(canonical, [])

    def add_user_wyceny(self, username: str, entry: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        if canonical not in self.wyceny:
            self.wyceny[canonical] = []
        
        entry["id"] = f"wyc-{len(self.wyceny[canonical]) + 101}"
        self.wyceny[canonical].insert(0, entry)
        self._save_json(WYCENY_FILE, self.wyceny)
        return entry

    def delete_user_wyceny(self, username: str, entry_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        items = self.wyceny.get(canonical, [])
        filtered = [x for x in items if x.get("id") != entry_id]
        if len(filtered) < len(items):
            self.wyceny[canonical] = filtered
            self._save_json(WYCENY_FILE, self.wyceny)
            return True
        return False

    # COMPANY DATA (STRICT PER-USER ISOLATION)
    def get_user_company(self, username: str) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        return self.company.get(canonical, DEFAULT_COMPANY.get(canonical, {}))

    def save_user_company(self, username: str, data: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        if canonical not in self.company:
            self.company[canonical] = {}
        self.company[canonical].update(data)
        self._save_json(COMPANY_FILE, self.company)
        return self.company[canonical]

user_data_mgr = UserDataManager()
