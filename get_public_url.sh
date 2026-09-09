#!/bin/bash

TUNNEL_LOG="/tmp/cloudflared_fomo.log"
PUBLIC_TXT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/PUBLIC_URL.txt"

echo "================================================================="
echo "  🌐 POBIERANIE AKTUALNEGO LINKU PUBLICZNEGO DLA ZNAJOMYCH"
echo "================================================================="

if [ -f "$PUBLIC_TXT" ] && [ -s "$PUBLIC_TXT" ]; then
    URL=$(cat "$PUBLIC_TXT")
    echo "  🌍 AKTUALNY LINK:  $URL"
    echo "  🔒 (Wyślij powyższy link znajomym - działa dopóki terminal jest otwarty)"
elif [ -f "$TUNNEL_LOG" ]; then
    URL=$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' "$TUNNEL_LOG" | grep -v 'api\.trycloudflare\.com' | grep -v 'www\.trycloudflare\.com' | head -n 1 || true)
    if [ -n "$URL" ]; then
        echo "  🌍 AKTUALNY LINK:  $URL"
        echo "$URL" > "$PUBLIC_TXT"
    else
        echo "  ⏳ Tunel się inicjalizuje... Spróbuj ponownie za 3 sekundy."
    fi
else
    echo "  ⚠️ Tunel nie jest uruchomiony. Uruchom najpierw: ./start.sh"
fi
echo "================================================================="
