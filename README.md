# 🐋 FOMO Whale Signal Bot (Sygnałowy Bot Grubasów > $500,000 USD)

Aplikacja bota sygnałowego wykrywająca **nowe coiny** pojawiające się na giełdzie / sieci **Robinhood Chain** (oraz Base, Solana, Monad) i dająca natychmiastowe sygnały, gdy inwestycją zainteresują się **Grubasi (osoby z portfelem powyżej $500,000 USD)**.

Każdy wygenerowany sygnał zawiera bezpośredni odnośnik do handlu tokenem na platformie **FOMO Family** (np. `https://fomo.family/tokens/robinhood/0x39dbed3a2bd333467115de45665cc57f813c4571`).

---

## ⚡ Szybkie Uruchomienie (Jednym Kliknięciem)

Aplikacja znajduje się w folderze `/Users/apple/Desktop/FOMO/fomo_whale_signal_bot` i jest w pełni **gotowa do odpalenia**:

### 🍏 macOS / Linux:
Otwórz Terminal w folderze projektu i uruchom:
```bash
./start.sh
```

### 🪟 Windows:
Kliknij dwukrotnie plik:
```cmd
start.bat
```

Skrypt automatycznie:
1. Utworzy wirtualne środowisko Python (`venv`).
2. Zainstaluje wymagane zależności z `requirements.txt`.
3. Przygotuje plik konfiguracyjny `.env`.
4. Uruchomi serwer aplikacji i skaner on-chain!

---

## 🌐 Panel Web Dashboard & Powiadomienia

Po uruchomieniu przejdź w przeglądarce pod adres:
👉 **[http://localhost:8000](http://localhost:8000)**

### Funkcje Dashboardu Web:
- **Powiadomienia Dźwiękowe (Audio Alerts)**: Sygnał audio w momencie pojawienia się nowego kupującego z portfelem > $500k USD.
- **Karty Sygnałów w Czasie Rzeczywistym**: Wyświetlają adres portfela grubasa, dokładny stan konta USD, kwotę zakupu, market cap i bezpośredni przycisk **"Open on FOMO"**.
- **Tabela Nowych Coinów**: Aktualna lista wykrytych tokenów z ceną, płynnością i statusem zainteresowania grubasów.

---

## ⚙️ Konfiguracja (`.env`)

Możesz łatwo dostosować progi i powiadomienia w pliku `.env`:

```env
# Próg klasyfikacji Grubasa (Domyślnie: $500,000 USD)
WHALE_MIN_PORTFOLIO_USD=500000.0

# Minimalna wartość pojedynczego zakupu w USD do natychmiastowego alertu
WHALE_MIN_BUY_USD=500.0

# Powiadomienia Telegram (Opcjonalne)
TELEGRAM_BOT_TOKEN=twoj_bot_token
TELEGRAM_CHAT_ID=twoj_chat_id

# Webhook Discord (Opcjonalny)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Węzeł RPC Robinhood Chain
RPC_ROBINHOOD=https://rpc.mainnet.chain.robinhood.com
```

---

## 🧪 Testy Jednostkowe

Aby zweryfikować działanie modułów aplikacji, uruchom:
```bash
source venv/bin/activate
python3 -m unittest discover -s tests
```

---

## 📁 Struktura Projektu

```
fomo_whale_signal_bot/
├── main.py                  # Główny serwer FastAPI & WebSocket Orchestrator
├── config.py                # Konfiguracja progów ($500k) i węzłów RPC
├── monitors/
│   ├── new_token_scanner.py # Skaner nowych tokenów i transferów on-chain
│   ├── whale_tracker.py     # Silnik weryfikacji portfela grubasów (> $500k)
│   └── fomo_api_client.py   # Klient API FOMO Family & DexScreener
├── notifiers/
│   ├── telegram_notifier.py # Powiadomienia Telegram Bot
│   ├── discord_notifier.py  # Powiadomienia Discord Webhook
│   └── console_notifier.py  # Panel konsolowy TUI (Rich)
├── web/
│   └── index.html           # Interaktywny panel Web Dashboard (WebSocket)
├── tests/
│   └── test_signal_bot.py   # Testy jednostkowe
├── start.sh                 # Skrypt startowy macOS / Linux
├── start.bat                # Skrypt startowy Windows
├── requirements.txt         # Wymagane biblioteki Python
└── .env                     # Zmienne środowiskowe
```
