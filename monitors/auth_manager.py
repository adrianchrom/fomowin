import os
import secrets
import json
import logging
from typing import Dict, Optional

from monitors.storage import LOCK, data_path, atomic_write_text, atomic_write_json

logger = logging.getLogger("AuthManager")

CREDENTIALS_FILE = data_path("CREDENTIALS.txt")
SESSIONS_FILE = data_path("SESSIONS.json")

# Hard cap of simultaneously valid sessions per account (oldest are dropped first).
MAX_SESSIONS_PER_USER = 25

DEFAULT_USERS = {
    "Adrian": "8492",
    "Maciek": "4729",
    "Karolina": "6183",
    "Patrycja": "9351",
    "Monika": "5274"
}

PIN_MAP = dict(DEFAULT_USERS)
USER_NAMES = {k.lower(): k for k in DEFAULT_USERS.keys()}

class AuthManager:
    def __init__(self):
        self.users: Dict[str, str] = dict(DEFAULT_USERS)
        self.active_sessions: Dict[str, str] = {} # token -> username
        self.init_credentials()
        self.load_sessions()

    def sync_mappings(self):
        """Keep PIN_MAP and USER_NAMES synchronized with self.users."""
        global PIN_MAP, USER_NAMES
        PIN_MAP.clear()
        USER_NAMES.clear()
        for u, p in self.users.items():
            PIN_MAP[str(p).strip()] = u
            USER_NAMES[u.lower()] = u

    def init_credentials(self):
        """Load or create default PINs for all users."""
        credentials_existed = os.path.exists(CREDENTIALS_FILE)
        if credentials_existed:
            # Start from the stored accounts only (not from the built-in defaults).
            self.users = {}
            try:
                with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        if ":" in line:
                            u, p = line.strip().split(":", 1)
                            clean_u = u.strip()
                            clean_p = p.strip()
                            if clean_u:
                                # If legacy alpha password in default users, migrate to canonical 4-digit PIN
                                if clean_u in DEFAULT_USERS and not clean_p.isdigit():
                                    clean_p = DEFAULT_USERS[clean_u]
                                self.users[clean_u] = clean_p
            except Exception as e:
                logger.error(f"Error reading credentials file: {e}")

        if not credentials_existed:
            # First start only: seed the built-in accounts. Afterwards the credentials file is the
            # single source of truth, so accounts deleted by the admin never come back after a restart.
            for u, p in DEFAULT_USERS.items():
                self.users.setdefault(u, p)
        else:
            # The super admin account must always exist and keep a valid PIN.
            if "Adrian" not in self.users or not str(self.users["Adrian"]).isdigit():
                self.users["Adrian"] = DEFAULT_USERS["Adrian"]
            # Repair broken PINs of existing accounts instead of resurrecting deleted ones.
            for u in list(self.users.keys()):
                if not str(self.users[u]).isdigit():
                    if u in DEFAULT_USERS:
                        self.users[u] = DEFAULT_USERS[u]
                    else:
                        del self.users[u]

        self.sync_mappings()
        self.save_credentials()

    def save_credentials(self):
        """Write current users and PINs to CREDENTIALS.txt."""
        try:
            with LOCK:
                atomic_write_text(CREDENTIALS_FILE, "".join(f"{u}:{p}\n" for u, p in self.users.items()))
        except Exception as e:
            logger.error(f"Error writing credentials file: {e}")

    def add_or_update_user(self, username: str, pin: str) -> str:
        """Add a new user or update existing user's PIN. PINs must be unique 4-digit codes."""
        clean_name = (username or "").strip()
        if clean_name and clean_name[0].islower():
            clean_name = clean_name[0].upper() + clean_name[1:]
        clean_pin = (pin or "").strip()
        if not clean_name:
            raise ValueError("Nazwa użytkownika nie może być pusta.")
        if not clean_pin.isdigit() or len(clean_pin) != 4:
            raise ValueError("Kod PIN musi mieć dokładnie 4 cyfry.")

        # PIN-only login requires every PIN to belong to exactly one account
        for existing_user, existing_pin in self.users.items():
            if existing_user.lower() != clean_name.lower() and str(existing_pin).strip() == clean_pin:
                raise ValueError("Ten kod PIN jest już przypisany do innego konta.")

        for k in list(self.users.keys()):
            if k.lower() == clean_name.lower():
                del self.users[k]

        self.users[clean_name] = clean_pin
        self.sync_mappings()
        self.save_credentials()
        return clean_name

    def delete_user(self, username: str) -> bool:
        """Delete user account (protecting Adrian)."""
        clean_name = (username or "").strip().lower()
        if clean_name == "adrian":
            return False  # Protect superadmin

        target_key = None
        for k in list(self.users.keys()):
            if k.lower() == clean_name:
                target_key = k
                break

        if target_key:
            del self.users[target_key]
            self.sync_mappings()
            self.save_credentials()
            # A deleted account must lose access immediately, also on devices that are still logged in.
            self.revoke_user_sessions(target_key)
            return True
        return False

    def revoke_user_sessions(self, username: str, keep_token: Optional[str] = None) -> int:
        """Invalidate every session of ``username`` (optionally keeping one token alive)."""
        target = (username or "").strip().lower()
        removed = 0
        with LOCK:
            for token, owner in list(self.active_sessions.items()):
                if (owner or "").lower() == target and token != keep_token:
                    del self.active_sessions[token]
                    removed += 1
            if removed:
                self.save_sessions()
        return removed

    def load_sessions(self):
        """Load persistent sessions from SESSIONS.json."""
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                    self.active_sessions = json.load(f)
            except Exception as e:
                logger.error(f"Error loading sessions: {e}")
                self.active_sessions = {}

    def save_sessions(self):
        """Save active sessions to SESSIONS.json."""
        atomic_write_json(SESSIONS_FILE, self.active_sessions)

    def get_canonical_user(self, username: str) -> str:
        u_clean = (username or "").strip()
        if not u_clean:
            return ""
        u_lower = u_clean.lower()
        for uname in self.users.keys():
            if uname.lower() == u_lower:
                return uname
        if u_lower in USER_NAMES:
            return USER_NAMES[u_lower]
        return u_clean.capitalize()

    def create_session(self, username: str) -> str:
        """Create a new session token for the given user."""
        canonical_user = self.get_canonical_user(username)
        if not canonical_user:
            return ""
        session_token = secrets.token_hex(24)
        with LOCK:
            self.active_sessions[session_token] = canonical_user
            # Keep the sessions file small: drop the oldest tokens of this user above the cap.
            own = [t for t, u in self.active_sessions.items() if u == canonical_user]
            for old in own[:-MAX_SESSIONS_PER_USER]:
                del self.active_sessions[old]
            self.save_sessions()
        return session_token

    def authenticate_user_pin(self, username: str, pin: str) -> Optional[tuple]:
        """Authenticate user strictly by username and matching assigned PIN."""
        clean_user = (username or "").strip()
        clean_pin = (pin or "").strip()
        if not clean_user or not clean_pin:
            return None

        # Match user case-insensitively
        matched_user = None
        for u in self.users.keys():
            if u.lower() == clean_user.lower():
                matched_user = u
                break

        if not matched_user:
            return None

        expected_pin = str(self.users[matched_user]).strip()
        if clean_pin == expected_pin:
            token = self.create_session(matched_user)
            return token, matched_user

        return None

    def authenticate_pin(self, pin: str, target_user: Optional[str] = None) -> Optional[tuple]:
        """Authenticate user strictly by PIN."""
        clean_pin = (pin or "").strip()
        if not clean_pin:
            return None

        if target_user:
            return self.authenticate_user_pin(target_user, clean_pin)

        # Check in self.users values
        for user_name, user_pin in self.users.items():
            if str(user_pin).strip() == clean_pin:
                canonical = self.get_canonical_user(user_name)
                token = self.create_session(canonical)
                return token, canonical

        # Check PIN_MAP
        if clean_pin in PIN_MAP:
            matched_user = self.get_canonical_user(PIN_MAP[clean_pin])
            token = self.create_session(matched_user)
            return token, matched_user

        return None

    def authenticate(self, username: str, password: str) -> Optional[tuple]:
        """Authenticate user strictly by valid username & PIN."""
        clean_pass = (password or "").strip()
        clean_user = (username or "").strip()

        # If username and password provided, authenticate as user + PIN
        if clean_user and clean_pass:
            res = self.authenticate_user_pin(clean_user, clean_pass)
            if res:
                return res

        if clean_pass in PIN_MAP or any(str(p).strip() == clean_pass for p in self.users.values()):
            return self.authenticate_pin(clean_pass)

        if clean_user in PIN_MAP or any(str(p).strip() == clean_user for p in self.users.values()):
            return self.authenticate_pin(clean_user)

        # Strict check against users dictionary
        for canonical_user, user_pin in self.users.items():
            if (canonical_user.lower() == clean_user.lower() or canonical_user.lower() == clean_pass.lower()) and (clean_pass == str(user_pin) or clean_user == str(user_pin)):
                token = self.create_session(canonical_user)
                return token, canonical_user

        return None

    def verify_session(self, session_token: Optional[str]) -> Optional[str]:
        """Verify session token and return username if valid."""
        if not session_token:
            return None
        username = self.active_sessions.get(session_token)
        if not username:
            return None
        # Sessions of accounts that no longer exist are worthless.
        if not any(u.lower() == username.lower() for u in self.users):
            return None
        return username

    def logout(self, session_token: Optional[str]):
        """Revoke a session token."""
        if session_token and session_token in self.active_sessions:
            del self.active_sessions[session_token]
            self.save_sessions()

    def logout_all(self):
        """Revoke all active sessions immediately."""
        self.active_sessions.clear()
        self.save_sessions()

auth_manager = AuthManager()
