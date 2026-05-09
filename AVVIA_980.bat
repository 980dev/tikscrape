@echo off
title 980 TIKSCRAPE PRO
echo ========================================
echo       980 TIKSCRAPE - PRO ENGINE
echo ========================================
echo.
echo Avvio in corso...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo Errore durante l'avvio. Controlla di aver installato i requisiti.
    pause
)
