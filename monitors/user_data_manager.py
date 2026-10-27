import copy
import json
import logging
import os
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

from monitors.storage import LOCK, data_path, atomic_write_json, load_json_file

logger = logging.getLogger("UserDataManager")

PERMISSIONS_FILE = data_path("USER_PERMISSIONS.json")
PROFILES_FILE = data_path("USER_PROFILES.json")
WYDATKI_FILE = data_path("DATA_WYDATKI.json")
WYCENY_FILE = data_path("DATA_WYCENY.json")
COMPANY_FILE = data_path("DATA_COMPANY.json")
KALENDARZ_FILE = data_path("DATA_KALENDARZ.json")
CRM_FILE = data_path("DATA_CRM.json")
TASKS_FILE = data_path("DATA_TASKS.json")
SETTINGS_FILE = data_path("DATA_USER_SETTINGS.json")
REVS_FILE = data_path("DATA_REVS.json")

MODULE_KEYS = ["fomo", "wydatki", "wyceny", "stopki_email", "kalendarz", "ai_chat", "crm", "tasks", "password_gen", "currency_calc"]

DEFAULT_PERMISSIONS = {
    "Adrian": {
        "fomo": True, "wydatki": True, "wyceny": True, "stopki_email": True, "kalendarz": True, "ai_chat": True, "crm": True, "tasks": True, "password_gen": True, "currency_calc": True, "is_admin": True
    },
    "Maciek": {
        "fomo": True, "wydatki": True, "wyceny": True, "stopki_email": True, "kalendarz": True, "ai_chat": True, "crm": True, "tasks": True, "password_gen": True, "currency_calc": True, "is_admin": False
    },
    "Karolina": {
        "fomo": True, "wydatki": True, "wyceny": True, "stopki_email": True, "kalendarz": True, "ai_chat": True, "crm": True, "tasks": True, "password_gen": True, "currency_calc": True, "is_admin": False
    },
    "Patrycja": {
        "fomo": True, "wydatki": True, "wyceny": True, "stopki_email": True, "kalendarz": True, "ai_chat": True, "crm": True, "tasks": True, "password_gen": True, "currency_calc": True, "is_admin": False
    },
    "Monika": {
        "fomo": False, "wydatki": True, "wyceny": False, "stopki_email": False, "kalendarz": False, "ai_chat": False, "crm": False, "tasks": False, "password_gen": False, "currency_calc": False, "is_admin": False
    }
}

DEFAULT_PROFILES = {
    "Adrian": {
        "p1": "Adrian",
        "p2": "Patrycja",
        "household": "PAIR_ADRIAN_PATRYCJA"
    },
    "Maciek": {
        "p1": "Maciek",
        "p2": "Karolina",
        "household": "PAIR_MACIEK_KAROLINA"
    },
    "Karolina": {
        "p1": "Maciek",
        "p2": "Karolina",
        "household": "PAIR_MACIEK_KAROLINA"
    },
    "Patrycja": {
        "p1": "Adrian",
        "p2": "Patrycja",
        "household": "PAIR_ADRIAN_PATRYCJA"
    },
    "Monika": {
        "p1": "Monika",
        "p2": "Tomek",
        "household": "PAIR_MONIKA_TOMEK"
    },
    "Tomek": {
        "p1": "Monika",
        "p2": "Tomek",
        "household": "PAIR_MONIKA_TOMEK"
    }
}

DEFAULT_COMPANY_DATA = {
    "name": "Biuro Usługowe / Twoja Firma",
    "address": "ul. Przykładowa 12/3, 00-001 Warszawa",
    "nip": "0000000000",
    "phone": "+48 000 000 000",
    "email": "biuro@firma.pl",
    "bank": "00 0000 0000 0000 0000 0000 0000",
    "logo_base64": ""
}

DEFAULT_COMPANY = {
    "Adrian": dict(DEFAULT_COMPANY_DATA),
    "Maciek": dict(DEFAULT_COMPANY_DATA),
    "Karolina": dict(DEFAULT_COMPANY_DATA),
    "Patrycja": dict(DEFAULT_COMPANY_DATA)
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

# Households that existed before household keys were introduced: their data was stored under a
# single person's name. ONLY these two may be migrated - every other household starts empty.
LEGACY_HOUSEHOLD_KEYS = {
    "PAIR_ADRIAN_PATRYCJA": "Adrian",
    "PAIR_MACIEK_KAROLINA": "Maciek",
}


def _new_id(prefix: str) -> str:
    """Collision-proof id (millisecond timestamp + random suffix)."""
    return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4]}"


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


class UserDataManager:
    """Manages persistent JSON storage & strict privacy isolation per user."""

    def __init__(self):
        self.permissions = load_json_file(PERMISSIONS_FILE, DEFAULT_PERMISSIONS, _is_dict)
        self.profiles = load_json_file(PROFILES_FILE, DEFAULT_PROFILES, _is_dict)
        self.wydatki = load_json_file(WYDATKI_FILE, DEFAULT_WYDATKI, _is_dict)
        self.wyceny = load_json_file(WYCENY_FILE, DEFAULT_WYCENY, _is_dict)
        self.company = load_json_file(COMPANY_FILE, DEFAULT_COMPANY, _is_dict)
        self.kalendarz = load_json_file(KALENDARZ_FILE, DEFAULT_KALENDARZ, _is_dict)
        self.crm = load_json_file(CRM_FILE, DEFAULT_CRM, _is_dict)
        self.tasks = load_json_file(TASKS_FILE, DEFAULT_TASKS, _is_dict)
        self.settings = load_json_file(SETTINGS_FILE, {}, _is_dict)
        # Revision counters of the "whole document" stores (used for conflict detection between
        # two devices / two members of one household editing the same document).
        self.revs: Dict[str, int] = load_json_file(REVS_FILE, {}, _is_dict)
        self._migrate_company_from_wyceny()

    def _migrate_company_from_wyceny(self):
        """Older versions stored the company profile inside the quotes document. If such a profile
        was customised but the company store still holds the defaults, move it over so that making
        the company store the single source of truth never loses what a user typed earlier."""
        changed = False
        with LOCK:
            for canonical, doc in list(self.wyceny.items()):
                if not isinstance(doc, dict) or not isinstance(doc.get("company"), dict):
                    continue
                embedded = self._normalize_company(doc["company"])
                stored = self.company.get(canonical, {})
                stored_is_default = all(
                    stored.get(k, DEFAULT_COMPANY_DATA[k]) == DEFAULT_COMPANY_DATA[k] for k in DEFAULT_COMPANY_DATA
                )
                embedded_is_custom = any(
                    embedded.get(k, DEFAULT_COMPANY_DATA[k]) != DEFAULT_COMPANY_DATA[k] for k in DEFAULT_COMPANY_DATA
                )
                if stored_is_default and embedded_is_custom:
                    self.company.setdefault(canonical, {}).update(embedded)
                    self.company[canonical].pop("logoBase64", None)
                    changed = True
            if changed:
                self._save_json(COMPANY_FILE, self.company)

    # ------------------------------------------------------------------ persistence helpers
    def _save_json(self, filepath: str, data: Any):
        atomic_write_json(filepath, data)

    def _load_json(self, filepath: str, default_data: dict) -> dict:  # kept for backwards compatibility
        return load_json_file(filepath, default_data, _is_dict)

    def get_rev(self, kind: str, key: str) -> int:
        return int(self.revs.get(f"{kind}:{key}", 0))

    def _bump_rev(self, kind: str, key: str) -> int:
        rev = self.get_rev(kind, key) + 1
        self.revs[f"{kind}:{key}"] = rev
        self._save_json(REVS_FILE, self.revs)
        return rev

    # ------------------------------------------------------------------ identity
    def resolve_canonical(self, username: str) -> str:
        u = (username or "").strip().lower()
        if u == "adrian": return "Adrian"
        if u == "maciek": return "Maciek"
        if u == "karolina": return "Karolina"
        if u == "patrycja": return "Patrycja"
        if u == "monika": return "Monika"
        if u == "tomek": return "Tomek"
        try:
            from monitors.auth_manager import auth_manager
            for k in auth_manager.users.keys():
                if k.lower() == u:
                    return k
        except Exception:
            pass
        return (username or "Użytkownik").strip().capitalize()

    # ------------------------------------------------------------------ permissions
    def get_user_permissions(self, username: str) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            changed = False
            if canonical not in self.permissions:
                restricted = canonical == "Monika"
                self.permissions[canonical] = {k: (not restricted or k == "wydatki") for k in MODULE_KEYS}
                self.permissions[canonical]["is_admin"] = False
                changed = True

            # Ensure keys exist
            for key in MODULE_KEYS:
                if key not in self.permissions[canonical]:
                    self.permissions[canonical][key] = (canonical != "Monika" or key == "wydatki")
                    changed = True
            if changed:
                self._save_json(PERMISSIONS_FILE, self.permissions)

            # Adrian always retains super admin access
            if canonical == "Adrian":
                full = {k: True for k in MODULE_KEYS}
                full["is_admin"] = True
                return full
            return self.permissions[canonical]

    def has_permission(self, username: str, module: str) -> bool:
        perms = self.get_user_permissions(username)
        if perms.get("is_admin"):
            return True
        return bool(perms.get(module, False))

    def update_user_permissions(self, username: str, new_perms: dict) -> dict:
        with LOCK:
            target = self.resolve_canonical(username)
            if target == "Adrian":
                return self.get_user_permissions("Adrian")

            if target not in self.permissions:
                self.permissions[target] = self.get_user_permissions(target).copy()

            for k in MODULE_KEYS:
                if k in new_perms:
                    self.permissions[target][k] = bool(new_perms[k])

            self.permissions[target]["is_admin"] = False
            self._save_json(PERMISSIONS_FILE, self.permissions)
            return self.permissions[target]

    def update_maciek_permissions(self, new_perms: dict) -> dict:
        return self.update_user_permissions("Maciek", new_perms)

    def get_all_users_permissions(self) -> dict:
        result = {}
        try:
            from monitors.auth_manager import auth_manager
            all_users = list(auth_manager.users.keys())
        except Exception:
            all_users = ["Maciek", "Karolina", "Patrycja", "Monika"]
        for u in all_users:
            if u.lower() != "adrian":
                result[u.lower()] = self.get_user_permissions(u)
        return result

    def delete_user_permissions(self, username: str):
        with LOCK:
            target = self.resolve_canonical(username)
            found_key = None
            for k in list(self.permissions.keys()):
                if k.lower() == username.strip().lower() or k.lower() == target.lower():
                    found_key = k
                    break
            if found_key and found_key.lower() != "adrian":
                del self.permissions[found_key]
                self._save_json(PERMISSIONS_FILE, self.permissions)
            self.delete_user_profile(username)

    # ------------------------------------------------------------------ profiles (display names & household)
    def get_user_profile(self, username: str) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            if canonical not in self.profiles:
                self.profiles[canonical] = {
                    "p1": canonical,
                    "p2": "Partner",
                    "household": f"PAIR_{canonical.upper()}"
                }
                self._save_json(PROFILES_FILE, self.profiles)
            return dict(self.profiles[canonical])

    def update_user_profile(self, username: str, profile_data: dict) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            current = self.get_user_profile(canonical)
            if "p1" in profile_data and profile_data["p1"]:
                current["p1"] = str(profile_data["p1"]).strip()
            if "p2" in profile_data and profile_data["p2"]:
                current["p2"] = str(profile_data["p2"]).strip()
            if "household" in profile_data and profile_data["household"]:
                current["household"] = str(profile_data["household"]).strip()
            self.profiles[canonical] = current
            self._save_json(PROFILES_FILE, self.profiles)
            return self.profiles[canonical]

    def delete_user_profile(self, username: str):
        with LOCK:
            canonical = self.resolve_canonical(username)
            if canonical in self.profiles and canonical.lower() != "adrian":
                del self.profiles[canonical]
                self._save_json(PROFILES_FILE, self.profiles)

    def get_all_users_profiles(self) -> dict:
        try:
            from monitors.auth_manager import auth_manager
            all_users = list(auth_manager.users.keys())
        except Exception:
            all_users = ["Adrian", "Maciek", "Karolina", "Patrycja", "Monika"]
        result = {}
        for u in all_users:
            result[u] = self.get_user_profile(u)
        return result

    def resolve_wydatki_user(self, username: str) -> str:
        u = (username or "").strip().lower()
        if u in ["adrian", "patrycja"]:
            default_hh = "PAIR_ADRIAN_PATRYCJA"
        elif u in ["monika", "tomek"]:
            default_hh = "PAIR_MONIKA_TOMEK"
        elif u in ["maciek", "karolina"]:
            default_hh = "PAIR_MACIEK_KAROLINA"
        else:
            default_hh = None

        canonical = self.resolve_canonical(username)
        if canonical in self.profiles and "household" in self.profiles[canonical]:
            hh = self.profiles[canonical]["household"]
            if hh:
                return hh

        if default_hh:
            return default_hh

        prof = self.get_user_profile(canonical)
        return prof.get("household", f"PAIR_{canonical.upper()}")

    # ------------------------------------------------------------------ WYDATKI (per-household budget)
    @staticmethod
    def _empty_wydatki() -> dict:
        return {"baseIncomes": [], "gigs": [], "expenses": []}

    def get_user_wydatki(self, username: str) -> dict:
        with LOCK:
            key = self.resolve_wydatki_user(username)
            val = self.wydatki.get(key)
            # One-off migration of the pre-household storage format. Only the two historical
            # households may inherit legacy data; everybody else must start with an EMPTY budget
            # (previously every new household silently received Maciek's budget).
            if val is None:
                legacy_key = LEGACY_HOUSEHOLD_KEYS.get(key)
                legacy_val = self.wydatki.get(legacy_key) if legacy_key else None
                if legacy_val is not None:
                    self.wydatki[key] = val = copy.deepcopy(legacy_val)
                    self._save_json(WYDATKI_FILE, self.wydatki)

            if isinstance(val, dict) and "baseIncomes" in val:
                val.setdefault("gigs", [])
                val.setdefault("expenses", [])
                return val

            expenses_list = val if isinstance(val, list) else []
            doc = self._empty_wydatki()
            doc["expenses"] = expenses_list
            return doc

    def get_user_wydatki_rev(self, username: str) -> int:
        return self.get_rev("wydatki", self.resolve_wydatki_user(username))

    @staticmethod
    def _sanitize_wydatki(data: dict) -> dict:
        clean = dict(data)
        for k in ("baseIncomes", "gigs", "expenses"):
            if not isinstance(clean.get(k), list):
                clean[k] = []
        return clean

    def save_user_wydatki(self, username: str, data: dict) -> dict:
        with LOCK:
            key = self.resolve_wydatki_user(username)
            self.wydatki[key] = self._sanitize_wydatki(data)
            self._save_json(WYDATKI_FILE, self.wydatki)
            self._bump_rev("wydatki", key)
            return self.wydatki[key]

    def save_user_wydatki_checked(self, username: str, data: dict, base_rev: Optional[int]) -> Tuple[bool, dict, int]:
        """Save only if ``base_rev`` is still current. Returns (saved, document, revision).

        When the revision is stale (the other household member / another device saved in the
        meantime) nothing is overwritten - the caller receives the current server document so the
        client can merge instead of destroying somebody else's changes.
        """
        with LOCK:
            key = self.resolve_wydatki_user(username)
            current_rev = self.get_rev("wydatki", key)
            if base_rev is not None and int(base_rev) != current_rev:
                return False, self.get_user_wydatki(username), current_rev
            doc = self.save_user_wydatki(username, data)
            return True, doc, self.get_rev("wydatki", key)

    def add_user_wydatki(self, username: str, entry: dict) -> dict:
        with LOCK:
            data = self.get_user_wydatki(username)
            if "expenses" not in data:
                data["expenses"] = []
            entry["id"] = _new_id("wyd")
            data["expenses"].insert(0, entry)
            self.save_user_wydatki(username, data)
            return entry

    def delete_user_wydatki(self, username: str, entry_id: str) -> bool:
        with LOCK:
            data = self.get_user_wydatki(username)
            items = data.get("expenses", [])
            filtered = [x for x in items if str(x.get("id")) != str(entry_id)]
            if len(filtered) < len(items):
                data["expenses"] = filtered
                self.save_user_wydatki(username, data)
                return True
            return False

    # ------------------------------------------------------------------ WYCENY (per-user quotes, stock, finances)
    def get_user_wyceny(self, username: str) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            val = self.wyceny.get(canonical)
            company = self.get_user_company(canonical)
            if isinstance(val, dict) and "quote" in val:
                # The company profile has ONE source of truth (the company store) so the quote
                # screen and the company settings can never drift apart.
                doc = dict(val)
                doc["company"] = company
                return doc

            return {
                "company": company,
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
                "inventory": [],
                "transactions": [],
                "historyQuotes": []
            }

    def get_user_wyceny_rev(self, username: str) -> int:
        return self.get_rev("wyceny", self.resolve_canonical(username))

    def save_user_wyceny(self, username: str, data: dict) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            doc = dict(data) if isinstance(data, dict) else {}
            for k in ("inventory", "transactions", "historyQuotes"):
                if not isinstance(doc.get(k), list):
                    doc[k] = []
            if not isinstance(doc.get("quote"), dict):
                doc["quote"] = {}
            incoming_company = doc.pop("company", None)
            if isinstance(incoming_company, dict) and incoming_company:
                self.save_user_company(canonical, self._normalize_company(incoming_company))
            self.wyceny[canonical] = doc
            self._save_json(WYCENY_FILE, self.wyceny)
            self._bump_rev("wyceny", canonical)
            out = dict(doc)
            out["company"] = self.get_user_company(canonical)
            return out

    def save_user_wyceny_checked(self, username: str, data: dict, base_rev: Optional[int]) -> Tuple[bool, dict, int]:
        with LOCK:
            canonical = self.resolve_canonical(username)
            current_rev = self.get_rev("wyceny", canonical)
            if base_rev is not None and int(base_rev) != current_rev:
                return False, self.get_user_wyceny(canonical), current_rev
            doc = self.save_user_wyceny(canonical, data)
            return True, doc, self.get_rev("wyceny", canonical)

    def add_user_wyceny(self, username: str, entry: dict) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            current = self.get_user_wyceny(canonical)
            if "items" in current.get("quote", {}):
                entry["id"] = _new_id("wyc")
                current["quote"]["items"].append(entry)
                self.save_user_wyceny(canonical, current)
            return entry

    def delete_user_wyceny(self, username: str, entry_id: str) -> bool:
        """Delete a saved quote (history) or - for backwards compatibility - a line item of the draft."""
        with LOCK:
            canonical = self.resolve_canonical(username)
            current = self.get_user_wyceny(canonical)

            history = current.get("historyQuotes", []) or []
            filtered_history = [x for x in history if str(x.get("id")) != str(entry_id)]
            if len(filtered_history) < len(history):
                current["historyQuotes"] = filtered_history
                self.save_user_wyceny(canonical, current)
                return True

            items = current.get("quote", {}).get("items", [])
            filtered = [x for x in items if str(x.get("id")) != str(entry_id)]
            if len(filtered) < len(items):
                current["quote"]["items"] = filtered
                self.save_user_wyceny(canonical, current)
                return True
            return False

    # ------------------------------------------------------------------ COMPANY (per-user)
    @staticmethod
    def _normalize_company(data: dict) -> dict:
        """Accept both ``logoBase64`` (browser) and ``logo_base64`` (server) spellings."""
        clean = dict(data)
        logo = clean.pop("logoBase64", None)
        if logo is not None:
            clean["logo_base64"] = logo
        return clean

    def get_user_company(self, username: str) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            if canonical in self.company:
                stored = dict(self.company[canonical])
                for k, v in DEFAULT_COMPANY_DATA.items():
                    stored.setdefault(k, v)
                stored["logoBase64"] = stored.get("logo_base64", "")
                return stored
            default = dict(DEFAULT_COMPANY_DATA)
            default["name"] = f"Firma – {canonical}"
            default["logoBase64"] = ""
            return default

    def save_user_company(self, username: str, data: dict) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            if canonical not in self.company:
                self.company[canonical] = {}
            self.company[canonical].update(self._normalize_company(data))
            self.company[canonical].pop("logoBase64", None)
            self._save_json(COMPANY_FILE, self.company)
            return self.get_user_company(canonical)

    # ------------------------------------------------------------------ generic per-user list stores
    def _get_list(self, store: dict, username: str) -> List[dict]:
        canonical = self.resolve_canonical(username)
        val = store.get(canonical)
        if isinstance(val, list):
            return val
        return []

    def _save_list(self, store: dict, filepath: str, username: str, items: List[dict]) -> List[dict]:
        with LOCK:
            canonical = self.resolve_canonical(username)
            store[canonical] = items
            self._save_json(filepath, store)
            return store[canonical]

    # KALENDARZ DATA (STRICT PER-USER ISOLATION)
    def get_user_kalendarz(self, username: str) -> List[dict]:
        return self._get_list(self.kalendarz, username)

    def save_user_kalendarz(self, username: str, events: List[dict]) -> List[dict]:
        return self._save_list(self.kalendarz, KALENDARZ_FILE, username, events)

    def add_user_kalendarz_event(self, username: str, event: dict) -> dict:
        with LOCK:
            events = self.get_user_kalendarz(username)
            if "id" not in event or not event["id"]:
                event["id"] = _new_id("ev")
            # idempotent: re-sending the same event (retry after a flaky connection) never duplicates it
            events = [e for e in events if str(e.get("id")) != str(event["id"])]
            events.append(event)
            self.save_user_kalendarz(username, events)
            return event

    def delete_user_kalendarz_event(self, username: str, event_id: str) -> bool:
        with LOCK:
            events = self.get_user_kalendarz(username)
            filtered = [x for x in events if str(x.get("id")) != str(event_id)]
            if len(filtered) < len(events):
                self.save_user_kalendarz(username, filtered)
                return True
            return False

    # CRM DATA (STRICT PER-USER ISOLATION)
    def get_user_crm(self, username: str) -> List[dict]:
        with LOCK:
            raw = self._get_list(self.crm, username)
            cleaned: List[dict] = []
            changed = False
            for c in raw:
                if not isinstance(c, dict):
                    changed = True
                    continue
                if str(c.get("name", "")).strip() in ("Updated Client", "Test Client"):
                    changed = True
                    continue
                if not c.get("id"):
                    c["id"] = _new_id("crm")
                    changed = True
                cleaned.append(c)
            if changed:
                self.save_user_crm(username, cleaned)
            return cleaned

    def save_user_crm(self, username: str, clients: List[dict]) -> List[dict]:
        return self._save_list(self.crm, CRM_FILE, username, clients)

    def add_user_crm_client(self, username: str, client: dict) -> dict:
        with LOCK:
            clients = self.get_user_crm(username)
            if "id" not in client or not client["id"]:
                client["id"] = _new_id("crm")
            clients = [c for c in clients if str(c.get("id")) != str(client["id"])]
            clients.append(client)
            self.save_user_crm(username, clients)
            return client

    def update_user_crm_client(self, username: str, client_id: str, updated_data: dict) -> Optional[dict]:
        with LOCK:
            clients = self.get_user_crm(username)
            for client in clients:
                if str(client.get("id")) == str(client_id):
                    client.update({k: v for k, v in updated_data.items() if k != "id"})
                    self.save_user_crm(username, clients)
                    return client
            return None

    def delete_user_crm_client(self, username: str, client_id: str) -> bool:
        with LOCK:
            clients = self.get_user_crm(username)
            filtered = [x for x in clients if str(x.get("id")) != str(client_id)]
            if len(filtered) < len(clients):
                self.save_user_crm(username, filtered)
                return True
            return False

    # TASKS (KANBAN / TODO) DATA (STRICT PER-USER ISOLATION)
    def get_user_tasks(self, username: str) -> List[dict]:
        with LOCK:
            raw = self._get_list(self.tasks, username)
            cleaned: List[dict] = []
            changed = False
            sample_titles = {"updated task", "test task", "przykładowe zadanie", "zadanie przykładowe", "sample task"}
            for t in raw:
                if not isinstance(t, dict):
                    changed = True
                    continue
                title_norm = str(t.get("title", "")).strip().lower()
                if title_norm in sample_titles:
                    changed = True
                    continue
                if not t.get("id"):
                    t["id"] = _new_id("task")
                    changed = True
                if not t.get("status"):
                    t["status"] = "todo"
                    changed = True
                cleaned.append(t)
            if changed:
                self.save_user_tasks(username, cleaned)
            return cleaned

    def save_user_tasks(self, username: str, task_list: List[dict]) -> List[dict]:
        return self._save_list(self.tasks, TASKS_FILE, username, task_list)

    def clear_user_tasks(self, username: str) -> bool:
        with LOCK:
            self.save_user_tasks(username, [])
            return True

    def add_user_task(self, username: str, task: dict) -> dict:
        with LOCK:
            task_list = self.get_user_tasks(username)
            if "id" not in task or not task["id"]:
                task["id"] = _new_id("task")
            if "status" not in task:
                task["status"] = "todo"
            task_list = [t for t in task_list if str(t.get("id")) != str(task["id"])]
            task_list.append(task)
            self.save_user_tasks(username, task_list)
            return task

    def update_user_task(self, username: str, task_id: str, updated_data: dict) -> Optional[dict]:
        with LOCK:
            task_list = self.get_user_tasks(username)
            for t in task_list:
                if str(t.get("id")) == str(task_id):
                    t.update({k: v for k, v in updated_data.items() if k != "id"})
                    self.save_user_tasks(username, task_list)
                    return t
            return None

    def delete_user_task(self, username: str, task_id: str) -> bool:
        with LOCK:
            task_list = self.get_user_tasks(username)
            filtered = [
                x for x in task_list
                if str(x.get("id")) != str(task_id) and str(x.get("title", "")).strip() != str(task_id).strip()
            ]
            if len(filtered) < len(task_list):
                self.save_user_tasks(username, filtered)
                return True
            return False

    # USER SETTINGS & MODULE PREFERENCES (STRICT PER-USER ISOLATION)
    def get_user_settings(self, username: str) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            val = self.settings.get(canonical)
            if isinstance(val, dict):
                return dict(val)
            return {}

    def save_user_settings(self, username: str, partial_settings: dict) -> dict:
        with LOCK:
            canonical = self.resolve_canonical(username)
            current = self.get_user_settings(canonical)
            if isinstance(partial_settings, dict):
                for k, v in partial_settings.items():
                    if isinstance(v, dict) and isinstance(current.get(k), dict):
                        merged = dict(current[k])
                        merged.update(v)
                        current[k] = merged
                    else:
                        current[k] = v
            self.settings[canonical] = current
            self._save_json(SETTINGS_FILE, self.settings)
            return dict(current)


user_data_mgr = UserDataManager()
