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
        "name": "Biuro Usługowe / Twoja Firma",
        "address": "ul. Przykładowa 12/3, 00-001 Warszawa",
        "nip": "0000000000",
        "phone": "+48 000 000 000",
        "email": "biuro@firma.pl",
        "bank": "00 0000 0000 0000 0000 0000 0000",
        "logo_base64": ""
    },
    "Maciek": {
        "name": "Biuro Usługowe / Twoja Firma",
        "address": "ul. Przykładowa 12/3, 00-001 Warszawa",
        "nip": "0000000000",
        "phone": "+48 000 000 000",
        "email": "biuro@firma.pl",
        "bank": "00 0000 0000 0000 0000 0000 0000",
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
    def get_user_wydatki(self, username: str) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        val = self.wydatki.get(canonical)
        if isinstance(val, dict) and "baseIncomes" in val:
            return val
        
        expenses_list = val if isinstance(val, list) else []
        if canonical == "Adrian":
            return {
                "baseIncomes": [
                    {"id": 1, "month": "2026-08", "p1": 9500, "p2": 8000, "adrian": 9500, "patrycja": 8000},
                    {"id": 2, "month": "2026-09", "p1": 9500, "p2": 8500, "adrian": 9500, "patrycja": 8500}
                ],
                "gigs": [
                    {"id": 1, "person": "Adrian", "title": "Zlecenie projektowe www", "amount": 2500, "month": "2026-09", "date": "2026-09-15"}
                ],
                "expenses": expenses_list
            }
        else:
            return {
                "baseIncomes": [
                    {"id": 1, "month": "2026-08", "p1": 8500, "p2": 7500, "maciek": 8500, "karolina": 7500},
                    {"id": 2, "month": "2026-09", "p1": 9000, "p2": 8000, "maciek": 9000, "karolina": 8000}
                ],
                "gigs": [
                    {"id": 1, "person": "Maciek", "title": "Projekt graficzny logo", "amount": 1800, "month": "2026-09", "date": "2026-09-14"}
                ],
                "expenses": expenses_list
            }

    def save_user_wydatki(self, username: str, data: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        self.wydatki[canonical] = data
        self._save_json(WYDATKI_FILE, self.wydatki)
        return self.wydatki[canonical]

    def add_user_wydatki(self, username: str, entry: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        data = self.get_user_wydatki(canonical)
        if "expenses" not in data:
            data["expenses"] = []
        entry["id"] = f"wyd-{len(data['expenses']) + 101}"
        data["expenses"].insert(0, entry)
        self.save_user_wydatki(canonical, data)
        return entry

    def delete_user_wydatki(self, username: str, entry_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        data = self.get_user_wydatki(canonical)
        items = data.get("expenses", [])
        filtered = [x for x in items if str(x.get("id")) != str(entry_id)]
        if len(filtered) < len(items):
            data["expenses"] = filtered
            self.save_user_wydatki(canonical, data)
            return True
        return False

    # WYCENY DATA (STRICT PER-USER ISOLATION & FULL POI PERSISTENCE)
    def get_user_wyceny(self, username: str) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        val = self.wyceny.get(canonical)
        if isinstance(val, dict) and "quote" in val:
            return val
        
        default_company = DEFAULT_COMPANY.get(canonical, {
            "name": "Biuro Usługowe / Twoja Firma",
            "address": "ul. Przykładowa 12/3, 00-001 Warszawa",
            "nip": "0000000000",
            "phone": "+48 000 000 000",
            "email": "biuro@firma.pl",
            "bank": "00 0000 0000 0000 0000 0000 0000",
            "logoBase64": ""
        })

        return {
            "company": default_company,
            "quote": {
                "number": "",
                "issueDate": "",
                "validDate": "",
                "clientName": "",
                "clientAddress": "",
                "clientPhone": "",
                "notes": "Wycena ważna przez 14 dni od daty wystawienia.\nPłatność po wykonaniu usługi lub ustaleniu etapowym.",
                "items": [
                    {"id": 1, "description": "Montaż instalacji / przykładowa pozycja usługi", "quantity": 1, "unit": "kpl.", "unitPrice": 450}
                ]
            },
            "inventory": [
                {"id": 1, "name": "Kabel YDYp 3x2.5 100m", "category": "Elektryka", "price": 340, "stock": 3, "link": "https://allegro.pl", "notes": "Zapas do punktów"},
                {"id": 2, "name": "Wkrętarka akumulatorowa 18V", "category": "Narzędzia", "price": 650, "stock": 1, "link": "", "notes": "Główny zestaw narzędzi"}
            ],
            "transactions": [
                {"id": 1, "date": "2026-09-15", "type": "income", "title": "Zlecenie u klienta (przykładowe)", "amount": 3500, "category": "Montaż"},
                {"id": 2, "date": "2026-09-15", "type": "expense", "title": "Zakup materiałów budowlanych", "amount": 840, "category": "Materiały"}
            ]
        }

    def save_user_wyceny(self, username: str, data: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        self.wyceny[canonical] = data
        self._save_json(WYCENY_FILE, self.wyceny)
        return self.wyceny[canonical]

    def add_user_wyceny(self, username: str, entry: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        current = self.get_user_wyceny(canonical)
        if "items" in current.get("quote", {}):
            entry["id"] = f"wyc-{Date.now() if 'Date' in globals() else 101}"
            current["quote"]["items"].append(entry)
            self.save_user_wyceny(canonical, current)
        return entry

    def delete_user_wyceny(self, username: str, entry_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        current = self.get_user_wyceny(canonical)
        items = current.get("quote", {}).get("items", [])
        filtered = [x for x in items if str(x.get("id")) != str(entry_id)]
        if len(filtered) < len(items):
            current["quote"]["items"] = filtered
            self.save_user_wyceny(canonical, current)
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
