#!/bin/bash

# Exit on error
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo ""
echo "================================================================="
echo "  🚀 URUCHAMIANIE FOMO WHALE & 0-30M PUMP SIGNAL BOT"
echo "================================================================="
echo ""

# 1. Czyszczenie starych procesów na porcie 8000
echo "🧹 [1/4] Czyszczenie portów i starych procesów..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
pkill -9 -f "main.py" 2>/dev/null || true
pkill -9 -f "cloudflared" 2>/dev/null || true
pkill -9 -f "localhost.run" 2>/dev/null || true

PUBLIC_TXT="$DIR/PUBLIC_URL.txt"
CRED_TXT="$DIR/CREDENTIALS.txt"
TUNNEL_LOG="/tmp/cloudflared_fomo.log"
APP_LOG="/tmp/fomo_app.log"
rm -f "$TUNNEL_LOG" "$PUBLIC_TXT" "$APP_LOG"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Błąd: Python 3 nie jest zainstalowany."
    exit 1
fi

# Create virtual environment if missing
if [ ! -d "venv" ]; then
    echo "📦 Tworzenie środowiska venv..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ ! -f ".env" ]; then
    cp .env.example .env
fi

# Pre-generate credentials if needed
python3 -c "from monitors.auth_manager import auth_manager; print('Auth initialized')" > /dev/null 2>&1 || true

# 2. Uruchomienie serwera FastAPI
echo "⚡ [2/4] Uruchamianie serwera aplikacji na http://localhost:8000..."
python3 main.py > "$APP_LOG" 2>&1 &
APP_PID=$!

# Funkcja czyszcząca przy zamknięciu terminala
cleanup() {
    echo -e "\n🛑 Zamykanie aplikacji..."
    kill $CF_PID $SSH_PID $APP_PID 2>/dev/null || true
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM EXIT

# Czekanie na dostępność serwera HTTP (max 10 sec)
SERVER_READY=false
for i in {1..10}; do
    if curl -s http://127.0.0.1:8000/api/status > /dev/null 2>&1; then
        SERVER_READY=true
        break
    fi
    sleep 1
done

if [ "$SERVER_READY" = true ]; then
    echo "✅ Serwer FastAPI działa prawidłowo."
else
    echo "⚠️ Serwer uruchamia się w tle..."
fi

# 3. Uruchomienie tunelu publicznego (SSH localhost.run / Cloudflare)
PUBLIC_URL=""
echo "🌐 [3/4] Tworzenie bezpiecznego linku publicznego dla znajomych..."

# Primary tunnel: SSH localhost.run (resolves 100% on all routers & ISPs without DNS blocks)
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8000 nokey@localhost.run > "$TUNNEL_LOG" 2>&1 &
SSH_PID=$!

for i in {1..8}; do
    if [ -f "$TUNNEL_LOG" ]; then
        MATCH_URL=$(grep -o 'https://[a-zA-Z0-9-]*\.lhr\.life' "$TUNNEL_LOG" | head -n 1 || true)
        if [ -n "$MATCH_URL" ]; then
            PUBLIC_URL="$MATCH_URL"
            break
        fi
    fi
    sleep 1
done

# Secondary Fallback: Cloudflare Tunnel
if [ -z "$PUBLIC_URL" ] && [ -f "./bin/cloudflared" ]; then
    chmod +x ./bin/cloudflared
    ./bin/cloudflared tunnel --url http://127.0.0.1:8000 >> "$TUNNEL_LOG" 2>&1 &
    CF_PID=$!

    for i in {1..8}; do
        if [ -f "$TUNNEL_LOG" ]; then
            MATCH_URL=$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' "$TUNNEL_LOG" | grep -v 'api\.trycloudflare\.com' | grep -v 'www\.trycloudflare\.com' | head -n 1 || true)
            if [ -n "$MATCH_URL" ]; then
                PUBLIC_URL="$MATCH_URL"
                break
            fi
        fi
        sleep 1
    done
fi

if [ -n "$PUBLIC_URL" ]; then
    echo "$PUBLIC_URL" > "$PUBLIC_TXT"
fi

echo ""
echo "================================================================="
echo "  🎉 APLIKACJA I TUNEL PUBLICZNY SĄ GOTOWE!"
echo "================================================================="
if [ -n "$PUBLIC_URL" ]; then
    echo "  🔗 LINK PUBLICZNY DLA ZNAJOMYCH:"
    echo "  👉  $PUBLIC_URL  👈"
else
    echo "  🏠 ADRES LOKALNY: http://localhost:8000"
fi
echo "================================================================="
echo "  🔑 DANE LOGOWANIA (ZAPISANE W CREDENTIALS.txt):"
if [ -f "$CRED_TXT" ]; then
    cat "$CRED_TXT" | while read -r line; do
        echo "     • $line"
    done
fi
echo "================================================================="
echo ""

# 4. Automatyczne otwarcie przeglądarki
TARGET_OPEN_URL="${PUBLIC_URL:-http://localhost:8000}"
echo "🚀 [4/4] Otwieranie przeglądarki z adresem: $TARGET_OPEN_URL..."

if command -v open &> /dev/null; then
    open "$TARGET_OPEN_URL"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$TARGET_OPEN_URL"
fi

echo ""
echo "📡 PODGLĄD LOGÓW I PRACY SKANERA NA ŻYWO (Ctrl+C aby wyłączyć):"
echo "-----------------------------------------------------------------"
tail -n 10 -f "$APP_LOG"
