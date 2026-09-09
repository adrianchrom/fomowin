@echo off
echo =================================================================
echo   🚀 Uruchamianie FOMO Whale Signal Bot (^> 500k $ Whale Alert)
echo =================================================================

cd /d %~dp0

if not exist venv (
    echo 📦 Tworzenie wirtualnego srodowiska venv...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo 📥 Instalacja wymaganych bibliotek...
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist .env (
    echo ⚙️ Tworzenie pliku .env...
    copy .env.example .env
)

echo =================================================================
echo   ✅ Srodowisko gotowe!
echo   🌐 Dashboard Web: http://localhost:8000
echo   🐋 Filtr Grubasow: ^> $500,000 USD
echo =================================================================

python main.py
pause
