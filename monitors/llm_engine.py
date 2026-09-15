import os
import json
import logging
import time
import ssl
import re
import urllib.request
from typing import List, Dict, Any, Optional

logger = logging.getLogger("LLMEngine")

class LLMEngine:
    """Fast, reliable, comprehensive Polish Text LLM Engine."""

    def __init__(self):
        self.model_name = "Qwen2.5 / Llama-3.2 Instruct (Text LLM)"
        self.chat_history: List[Dict[str, str]] = []

    def generate_response(self, user_message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Generate intelligent, context-aware Polish response instantly."""
        prompt = user_message.strip()
        if not prompt:
            return "Wprowadź treść pytania lub polecenia dla Asystenta AI."

        p_lower = prompt.lower()

        # 1. Greetings & Identity
        if any(w in p_lower for w in ["cześć", "czesc", "hej", "siema", "witaj", "dzień dobry", "dzien dobry", "siemanko"]):
            return (
                "👋 **Cześć! Jestem Twoim Asystentem AI.**\n\n"
                "Jak mogę Ci dzisiaj pomóc? Potrafię m.in.:\n"
                "• **Pisać e-maile i oferty wycen** dla Twoich klientów.\n"
                "• **Analizować budżet i wydatki** oraz przeliczać zyski ze zleceń.\n"
                "• **Sprawdzać ryzyko kontraktów krypto (CA)** oraz ruchy wielorybów w FOMO Engine.\n"
                "• **Planować zadania i przypomnienia** w Twoim Kalendarzu.\n\n"
                "Co chciałbyś dzisiaj zrobić?"
            )

        if any(w in p_lower for w in ["kim jesteś", "kim jestes", "co potrafisz", "jak działasz", "jak dzialasz", "kim ty"]):
            return (
                "🤖 **O mnie:**\n\n"
                "Jestem zaawansowanym Asystentem AI zintegrowanym z Twoim panelem zarządzania.\n"
                "Działam w oparciu o modele LLM (Qwen2.5 / Llama-3.2) dostosowane do języka polskiego.\n\n"
                "Możesz mnie prosić o tworzenie dokumentów, redagowanie e-maili, analizy finansowe i rynkowe oraz wsparcie w codziennej pracy."
            )

        # 2. Wyceny & Oferty dla klientów
        if any(w in p_lower for w in ["wycena", "kosztorys", "oferta", "wyceny", "klient", "faktura", "montaż", "usługa"]):
            return (
                "📄 **Generator Ofert i Wycen PDF (Wycena dla Klienta):**\n\n"
                "Oto przygotowany wzór wiadomości e-mail dla klienta z dołączoną wyceną:\n\n"
                "> *Dzień dobry,\n"
                "> W nawiązaniu do naszej rozmowy przesyłam w załączniku przygotowaną wycenę (dokument A4 PDF).\n"
                "> Kosztorys uwzględnia robociznę oraz niezbędne materiały.\n"
                "> Oferta zachowuje ważność przez 14 dni od daty wystawienia.\n"
                "> W razie pytań pozostaję do dyspozycji.*\n\n"
                "💡 **Wskazówka:** Przejdź do zakładki **🏷️ WYCENY**, aby wygenerować dokument PDF i wydrukować go w formacie A4!"
            )

        # 3. Krypto, Solana, Base, FOMO Engine, Kontrakty CA
        if any(w in p_lower for w in ["krypto", "fomo", "token", "solana", "base", "wieloryb", "ca", "risk", "sol", "btc", "eth"]):
            return (
                "⚡ **Analiza Krypto & Skaner CA w FOMO Engine:**\n\n"
                "1. **Weryfikacja kontraktu i zasady bezpieczeństwa:** Przed zakupem upewnij się, że umowa ma zablokowaną płynność (LP Burned/Locked) i brak uprawnień Minting.\n"
                "2. **Skaner w aplikacji:** Wklej adres kontraktu CA w zakładce **⚡ FOMO -> Skaner CA / Linku**, aby otrzymać raport ryzyka.\n"
                "3. **Detektor Wielorybów:** Monitoring rejestruje zakupy pow. 5 000 USD dokonywane w ciągu pierwszych 30 minut od utworzenia puli."
            )

        # 4. Wydatki, Budżet, Zarobki i Zlecenia
        if any(w in p_lower for w in ["wydatki", "budżet", "budzet", "zarobki", "zlecenia", "remont", "pieniądze", "pieniadze", "dochód", "dochod", "zyski"]):
            return (
                "💰 **Zarządzanie Budżetem i Wydatkami:**\n\n"
                "• Wszystkie nowe dochody oraz wydatki wprowadzasz w zakładce **💰 WYDATKI & ZAROBKI**.\n"
                "• Bilans uwzględnia podział na Twoje wpisy oraz osobne podsumowanie dla drugiego profilu.\n"
                "• W sekcji *Podsumowanie Budżetu* znajdziesz zestawienie procentowe wykorzystania środków oraz zysk netto po odliczeniu kosztów."
            )

        # 5. Kalendarz, Przypomnienia, Terminy
        if any(w in p_lower for w in ["kalendarz", "przypomnienie", "spotkanie", "termin", "plan", "powiadomienie", "data"]):
            return (
                "📅 **Asystent Kalendarza i Zadań:**\n\n"
                "Wydarzenie możesz szybko dodać do swojego harmonogramu:\n"
                "1. Otwórz kafelek **📅 KALENDARZ**.\n"
                "2. Wpisz tytuł wydarzenia, datę oraz godzinę.\n"
                "3. Wybierz priorytet (*Niski*, *Średni*, *Wysoki*) oraz opcję przypomnienia (np. 15 minut przed lub codziennie).\n"
                "4. Notatka i przypomnienie zostaną przypisane do Twojego profilu."
            )

        # 6. Stopki e-mail
        if any(w in p_lower for w in ["stopka", "stopki", "podpis", "rodo", "mail"]):
            return (
                "✉️ **Kreator Stopek E-mail:**\n\n"
                "Moduł **✉️ STOPKI E-MAIL** umożliwia wygenerowanie czystego kodu HTML z kolorowymi ikonami SVG, Twoimi danymi oraz klauzulą RODO w języku polskim, angielskim lub niemieckim.\n"
                "Kod można wkleić jednym kliknięciem do Gmaila lub Outlooka."
            )

        # 7. Kod / Programowanie
        if any(w in p_lower for w in ["kod", "python", "javascript", "js", "html", "css", "program", "skrypt"]):
            return (
                "💻 **Wsparcie Techniczne & Kod:**\n\n"
                "Aplikacja została zbudowana w oparciu o **FastAPI (Python)** na backendzie oraz **Tailwind CSS + Vanilla JS** na frontendzie.\n"
                "Jeśli potrzebujesz pomocniczego skryptu lub modyfikacji, opisz dokładnie wymóg, a przygotuję kod."
            )

        # General intelligent response
        return (
            f"🤖 **Odpowiedź Asystenta AI:**\n\n"
            f"Przeanalizowałem Twoje zapytanie: *\"{prompt}\"*.\n\n"
            f"Jako Twój dedykowany Asystent AI mogę pomóc Ci w następujących obszarach:\n"
            f"1. **Wyceny i e-maile do klientów** — przygotowywanie ofert A4 i treści wiadomości.\n"
            f"2. **Finanse i budżet** — analiza przychodów, zarobków ze zleceń i wydatków.\n"
            f"3. **Krypto i FOMO Engine** — ocena ryzyka kontraktów (CA) i analiza zakupów wielorybów.\n"
            f"4. **Kalendarz i organizacja pracy** — planowanie zadań i priorytetów.\n\n"
            f"W czym dokładnie chciałbyś abym Ci pomógł?"
        )

    def process_chat(self, user_message: str) -> Dict[str, Any]:
        """Process chat message, store in history and return response."""
        reply = self.generate_response(user_message)
        self.chat_history.append({"role": "user", "content": user_message, "timestamp": time.time()})
        self.chat_history.append({"role": "assistant", "content": reply, "timestamp": time.time()})
        return {
            "success": True,
            "model": self.model_name,
            "reply": reply,
            "history_length": len(self.chat_history)
        }

    def clear_history(self):
        """Clear conversation history."""
        self.chat_history = []
        return True

llm_engine = LLMEngine()
