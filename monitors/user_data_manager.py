import os
import json
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("UserDataManager")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PERMISSIONS_FILE = os.path.join(BASE_DIR, "USER_PERMISSIONS.json")
WYDATKI_FILE = os.path.join(BASE_DIR, "DATA_WYDATKI.json")
WYCENY_FILE = os.path.join(BASE_DIR, "DATA_WYCENY.json")
COMPANY_FILE = os.path.join(BASE_DIR, "DATA_COMPANY.json")
KALENDARZ_FILE = os.path.join(BASE_DIR, "DATA_KALENDARZ.json")
CRM_FILE = os.path.join(BASE_DIR, "DATA_CRM.json")
TASKS_FILE = os.path.join(BASE_DIR, "DATA_TASKS.json")

DEFAULT_PERMISSIONS = {
    "Adrian": {
        "fomo": True,
        "wydatki": True,
        "wyceny": True,
        "stopki_email": True,
        "kalendarz": True,
        "ai_chat": True,
        "crm": True,
        "tasks": True,
        "password_gen": True,
        "currency_calc": True,
        "is_admin": True
    },
    "Maciek": {
        "fomo": True,
        "wydatki": False,
        "wyceny": False,
        "stopki_email": False,
        "kalendarz": False,
        "ai_chat": True,
        "crm": True,
        "tasks": True,
        "password_gen": True,
        "currency_calc": True,
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
    "Adrian": {
        "baseIncomes": [],
        "gigs": [],
        "expenses": []
    },
    "Maciek": {
        "baseIncomes": [],
        "gigs": [],
        "expenses": []
    }
}

DEFAULT_WYCENY = {
    "Adrian": {},
    "Maciek": {}
}

DEFAULT_KALENDARZ = {
    "Adrian": [],
    "Maciek": []
}

DEFAULT_CRM = {
    "Adrian": [],
    "Maciek": []
}

DEFAULT_TASKS = {
    "Adrian": [],
    "Maciek": []
}

class UserDataManager:
    """Manages persistent JSON storage & strict privacy isolation per user."""

    def __init__(self):
        self.permissions = self._load_json(PERMISSIONS_FILE, DEFAULT_PERMISSIONS)
        self.wydatki = self._load_json(WYDATKI_FILE, DEFAULT_WYDATKI)
        self.wyceny = self._load_json(WYCENY_FILE, DEFAULT_WYCENY)
        self.company = self._load_json(COMPANY_FILE, DEFAULT_COMPANY)
        self.kalendarz = self._load_json(KALENDARZ_FILE, DEFAULT_KALENDARZ)
        self.crm = self._load_json(CRM_FILE, DEFAULT_CRM)
        self.tasks = self._load_json(TASKS_FILE, DEFAULT_TASKS)

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
                "kalendarz": False,
                "ai_chat": True,
                "crm": True,
                "tasks": True,
                "password_gen": True,
                "currency_calc": True,
                "is_admin": False
            }
            self._save_json(PERMISSIONS_FILE, self.permissions)
        
        # Ensure keys exist
        for key in ["kalendarz", "ai_chat", "crm", "tasks", "password_gen", "currency_calc"]:
            if key not in self.permissions[canonical]:
                self.permissions[canonical][key] = True
                self._save_json(PERMISSIONS_FILE, self.permissions)

        # Adrian always retains super admin access
        if canonical == "Adrian":
            return {
                "fomo": True,
                "wydatki": True,
                "wyceny": True,
                "stopki_email": True,
                "kalendarz": True,
                "ai_chat": True,
                "crm": True,
                "tasks": True,
                "password_gen": True,
                "currency_calc": True,
                "is_admin": True
            }
        return self.permissions[canonical]

    def update_maciek_permissions(self, new_perms: dict) -> dict:
        target = "Maciek"
        if target not in self.permissions:
            self.permissions[target] = {}
        
        for k in ["wydatki", "wyceny", "stopki_email", "kalendarz", "ai_chat", "crm", "tasks", "password_gen", "currency_calc"]:
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
        return {
            "baseIncomes": [],
            "gigs": [],
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
        entry["id"] = f"wyd-{int(time.time() * 1000)}"
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
            ],
            "historyQuotes": []
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
            entry["id"] = f"wyc-{int(time.time() * 1000)}"
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

    # KALENDARZ DATA (STRICT PER-USER ISOLATION)
    def get_user_kalendarz(self, username: str) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        val = self.kalendarz.get(canonical)
        if isinstance(val, list):
            return val
        return []

    def save_user_kalendarz(self, username: str, events: List[dict]) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        self.kalendarz[canonical] = events
        self._save_json(KALENDARZ_FILE, self.kalendarz)
        return self.kalendarz[canonical]

    def add_user_kalendarz_event(self, username: str, event: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        events = self.get_user_kalendarz(canonical)
        if "id" not in event or not event["id"]:
            event["id"] = f"ev-{int(time.time() * 1000)}"
        events.append(event)
        self.save_user_kalendarz(canonical, events)
        return event

    def delete_user_kalendarz_event(self, username: str, event_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        events = self.get_user_kalendarz(canonical)
        filtered = [x for x in events if str(x.get("id")) != str(event_id)]
        if len(filtered) < len(events):
            self.save_user_kalendarz(canonical, filtered)
            return True
        return False

    # CRM DATA (STRICT PER-USER ISOLATION)
    def get_user_crm(self, username: str) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        val = self.crm.get(canonical)
        if isinstance(val, list):
            return val
        return []

    def save_user_crm(self, username: str, clients: List[dict]) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        self.crm[canonical] = clients
        self._save_json(CRM_FILE, self.crm)
        return self.crm[canonical]

    def add_user_crm_client(self, username: str, client: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        clients = self.get_user_crm(canonical)
        if "id" not in client or not client["id"]:
            client["id"] = f"crm-{int(time.time() * 1000)}"
        clients.append(client)
        self.save_user_crm(canonical, clients)
        return client

    def update_user_crm_client(self, username: str, client_id: str, updated_data: dict) -> Optional[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        clients = self.get_user_crm(canonical)
        for client in clients:
            if str(client.get("id")) == str(client_id):
                client.update(updated_data)
                self.save_user_crm(canonical, clients)
                return client
        return None

    def delete_user_crm_client(self, username: str, client_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        clients = self.get_user_crm(canonical)
        filtered = [x for x in clients if str(x.get("id")) != str(client_id)]
        if len(filtered) < len(clients):
            self.save_user_crm(canonical, filtered)
            return True
        return False

    # TASKS (KANBAN / TODO) DATA (STRICT PER-USER ISOLATION)
    def get_user_tasks(self, username: str) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        val = self.tasks.get(canonical)
        if isinstance(val, list):
            return val
        return []

    def save_user_tasks(self, username: str, task_list: List[dict]) -> List[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        self.tasks[canonical] = task_list
        self._save_json(TASKS_FILE, self.tasks)
        return self.tasks[canonical]

    def add_user_task(self, username: str, task: dict) -> dict:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        task_list = self.get_user_tasks(canonical)
        if "id" not in task or not task["id"]:
            task["id"] = f"task-{int(time.time() * 1000)}"
        if "status" not in task:
            task["status"] = "todo"
        task_list.append(task)
        self.save_user_tasks(canonical, task_list)
        return task

    def update_user_task(self, username: str, task_id: str, updated_data: dict) -> Optional[dict]:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        task_list = self.get_user_tasks(canonical)
        for t in task_list:
            if str(t.get("id")) == str(task_id):
                t.update(updated_data)
                self.save_user_tasks(canonical, task_list)
                return t
        return None

    def delete_user_task(self, username: str, task_id: str) -> bool:
        canonical = "Adrian" if username.lower() == "adrian" else "Maciek"
        task_list = self.get_user_tasks(canonical)
        filtered = [x for x in task_list if str(x.get("id")) != str(task_id)]
        if len(filtered) < len(task_list):
            self.save_user_tasks(canonical, filtered)
            return True
        return False

user_data_mgr = UserDataManager()
